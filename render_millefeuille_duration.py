#!/usr/bin/env python3
"""Rend un WAV à partir du JSON de durée rg2sing, avec choix de chanteuse et vocodeur.

Validation de l'intégration dsdur -> dsacoustic -> NSF-HiFiGAN.
Cette maquette utilise une hauteur stable par groupe ; elle ne remplace pas dspitch.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import soundfile as sf
import yaml


def new_session(path, use_profile=False):
    opts = ort.SessionOptions()
    opts.enable_profiling = use_profile
    sess = ort.InferenceSession(str(path), sess_options=opts,
                                providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    sess.disable_fallback()
    if "CUDAExecutionProvider" not in sess.get_providers():
        raise RuntimeError("CUDA non disponible")
    return sess


def show_profile(session):
    path = Path(session.end_profiling())
    events = json.loads(path.read_text())
    counts = {}
    for e in events:
        if e.get("cat") == "Node":
            p = e.get("args", {}).get("provider", "inconnu")
            counts[p] = counts.get(p, 0) + 1
    path.unlink(missing_ok=True)
    print("Exécution ONNX :", counts)
    if not counts.get("CUDAExecutionProvider"):
        raise RuntimeError("Aucun nœud exécuté sur CUDA")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="/output/duree_diagnostic.json")
    ap.add_argument("--output", default="/output/test_deux_syllabes.wav")
    ap.add_argument("--root", default="/models/UFR-V1.0/UFR-V1.0")
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--depth", type=float, default=0.6)
    ap.add_argument("--profile", action="store_true")
    ap.add_argument("--features-out", default=None,
                    help="Écrire mel et f0 dans un NPZ pour comparer les vocodeurs (identiques)")
    ap.add_argument("--features-in", default=None,
                    help="Relire mel et f0 depuis un NPZ, sans recalculer l’acoustique")
    ap.add_argument("--singer", default="MonteCristo_ALYS", help="Répertoire de la chanteuse sous --root")
    ap.add_argument("--speaker", default=None, help="Nom ou chemin relatif du speaker dans dsconfig.yaml")
    ap.add_argument("--vocoder", choices=["nsf", "potluck", "tgm"], default="nsf")
    ap.add_argument("--pitch-mode", choices=["flat", "model"], default="flat")
    ap.add_argument("--pitch-steps", type=int, default=10)
    ap.add_argument("--pitch-seed", type=int, default=12345)
    ap.add_argument("--pitch-csv", default=None)
    ap.add_argument("--inspect-pitch", action="store_true", help="Afficher les signatures ONNX dspitch puis quitter")
    a = ap.parse_args()
    if not 1 <= a.steps <= 100 or not 0 < a.depth <= .6:
        ap.error("steps dans [1,100], depth dans ]0,.6]")
    if a.features_in and a.features_out:
        ap.error("--features-in et --features-out sont mutuellement exclusifs")
    if a.pitch_mode == "model" and a.singer != "MonteCristo_ALYS":
        ap.error("dspitch utilise encore l'embedding ALYS; rester en --pitch-mode flat pour comparer les chanteuses")
    doc = json.loads(Path(a.input).read_text(encoding="utf8"))
    if doc["sample_rate"] != 44100 or doc["hop_size"] != 512:
        raise ValueError("Paramètres audio incompatibles avec la banque")
    groups, group_midi, phones = doc["groups"], doc["midi"], doc["phonemes"]
    if len(groups) != len(group_midi) or sum(len(g) for g in groups) != len(phones):
        raise ValueError("Incohérence des groupes et phonèmes")
    tokens = [p["phoneme"] for p in phones]
    if tokens != [p for g in groups for p in g]:
        raise ValueError("Ordre des phonèmes incorrect")
    durations = [int(p["frames"]) for p in phones]
    if min(durations) < 1:
        raise ValueError("Durée de phonème nulle")
    root = Path(a.root)
    core = root / "0_CORE"
    mapping = json.loads((core / "dsacoustic/millefeuille_v001.phonemes.json").read_text())
    languages = json.loads((core / "dsacoustic/millefeuille_v001.languages.json").read_text())
    missing = [p for p in tokens if p not in mapping]
    if missing:
        raise ValueError(f"Phonèmes absents du modèle : {missing}")
    singer_dir = root / a.singer
    config_path = singer_dir / "dsconfig.yaml"
    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration de chanteuse introuvable : {config_path}")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    speakers = config.get("speakers", [])
    if not speakers:
        raise ValueError(f"Aucun speaker dans {config_path}")
    # Un speaker est un chemin relatif dans le fichier dsconfig.yaml.
    if a.speaker is None:
        speaker = speakers[0]
    else:
        matches = [s for s in speakers if s == a.speaker or Path(s).name == a.speaker or Path(s).stem == a.speaker]
        if len(matches) != 1:
            raise ValueError(f"Speaker {a.speaker!r} non reconnu. Choix : {speakers}")
        speaker = matches[0]
    emb_path = singer_dir / (speaker + ".emb")
    if not emb_path.is_file():
        raise FileNotFoundError(f"Embedding vocal introuvable : {emb_path}")
    emb = np.fromfile(emb_path, dtype="<f4")
    if emb.size != 256 or not np.isfinite(emb).all():
        raise ValueError(f"Embedding acoustique incorrect : {emb_path} ({emb.size} flottants)")
    # Vérifier les caractéristiques du spectrogramme avant toute comparaison.
    common = {
        "sample_rate":44100, "hop_size":512, "fft_size":2048, "win_size":2048,
        "num_mel_bins":128, "mel_fmin":40, "mel_fmax":16000,
        "mel_base":"e", "mel_scale":"slaney"
    }
    voc_dir = core / "dsvocoder" / a.vocoder
    voc_cfg_path = voc_dir / "vocoder.yaml"
    if not voc_cfg_path.is_file():
        raise FileNotFoundError(voc_cfg_path)
    voc_cfg = yaml.safe_load(voc_cfg_path.read_text(encoding="utf-8"))
    for k, expected in common.items():
        if config.get(k) != expected or voc_cfg.get(k) != expected:
            raise ValueError(f"Paramètre incompatible {k}: singer={config.get(k)!r} vocoder={voc_cfg.get(k)!r} attendu={expected!r}")
    # Le champ model de certains vocoder.yaml est relatif au répertoire de la banque,
    # et non au fichier YAML lui-même. Retrouver strictement le modèle dans son dossier.
    candidates = list(voc_dir.glob("*.onnx"))
    target_name = Path(voc_cfg["model"]).name
    voc_models = [p for p in candidates if p.name == target_name]
    if len(voc_models) != 1:
        raise FileNotFoundError(f"Modèle de vocodeur {target_name} absent dans {voc_dir} ; trouvés={candidates}")
    voc_path = voc_models[0]
    print(f"Chanteuse : {a.singer} ; speaker : {speaker} ; vocodeur : {a.vocoder}")
    pitches = []
    for item, midi in zip(phones, [m for g, m in zip(groups, group_midi) for _ in g]):
        f0 = 0.0 if item["phoneme"] in ("SP", "AP", "EP") or midi <= 0 else 440.0 * (2.0 ** ((midi-69) / 12.0))
        pitches.extend([f0] * int(item["frames"]))
    f0 = np.array(pitches, dtype=np.float32)[None, :]
    if a.features_in:
        with np.load(a.features_in, allow_pickle=False) as data:
            if set(data.files) != {"mel", "f0"}:
                raise ValueError("NPZ incompatible : seules les entrées mel et f0 sont attendues")
            mel = np.asarray(data["mel"], dtype=np.float32)
            f0 = np.asarray(data["f0"], dtype=np.float32)
        if f0.ndim != 2 or f0.shape[0] != 1 or mel.shape != (1, f0.shape[1], 128):
            raise ValueError(f"Dimensions de features incompatibles : mel={mel.shape} f0={f0.shape}")
        if not np.isfinite(mel).all() or not np.isfinite(f0).all():
            raise ValueError("Features non finies")
        print(f"Features relues : {a.features_in}; mel={mel.shape}, f0={f0.shape}")
    else:
        if a.pitch_mode == "model" or a.inspect_pitch:
            from millefeuille_pitch import predict_pitch
            predicted = predict_pitch(doc, root, new_session,
                                      profile=a.profile, steps=a.pitch_steps,
                                      seed=a.pitch_seed, pitch_output=a.pitch_csv,
                                      inspect_only=a.inspect_pitch)
            if a.inspect_pitch:
                return
            f0, diagnostics = predicted
            print("Hauteur dspitch :", diagnostics)
        n_frames = f0.shape[1]
        feed = {
            "tokens": np.array([[mapping[p] for p in tokens]], dtype=np.int64),
            "languages": np.full((1,len(tokens)), languages["fr"], dtype=np.int64),
            "durations": np.array([durations], dtype=np.int64),
            "f0": f0,
            "gender": np.zeros((1,n_frames),dtype=np.float32),
            "velocity": np.ones((1,n_frames),dtype=np.float32),
            "spk_embed": np.broadcast_to(emb[None,None,:],(1,n_frames,256)).copy(),
            "depth": np.array(a.depth,dtype=np.float32),
            "steps": np.array(a.steps,dtype=np.int64),
        }
        acoustic = new_session(core / "dsacoustic/millefeuille_v001.onnx", a.profile)
        start = time.perf_counter()
        mel = acoustic.run(["mel"], feed)[0]
        print(f"Acoustique : {time.perf_counter()-start:.3f}s ; mel={mel.shape}, plage=[{mel.min():.3f},{mel.max():.3f}]")
        if mel.shape != (1,n_frames,128) or not np.isfinite(mel).all():
            raise RuntimeError("Spectrogramme invalide")
        if a.profile: show_profile(acoustic)
        del acoustic
        if a.features_out:
            fp = Path(a.features_out)
            fp.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(fp, mel=mel, f0=f0)
            print("Features sauvegardées :", fp)
    vocoder = new_session(voc_path, a.profile)
    inputs = {m.name: m for m in vocoder.get_inputs()}
    if set(inputs) != {"mel", "f0"}:
        raise RuntimeError(f"Signature du vocodeur non prévue : {[(m.name, m.shape, m.type) for m in vocoder.get_inputs()]}")
    start = time.perf_counter()
    outputs = [m.name for m in vocoder.get_outputs()]
    if "waveform" not in outputs:
        raise RuntimeError(f"Sorties vocodeur non prévues : {outputs}")
    wave = vocoder.run(["waveform"], {"mel":mel,"f0":f0})[0].reshape(-1)
    print(f"Vocodeur : {time.perf_counter()-start:.3f}s ; durée={len(wave)/44100:.3f}s")
    if a.profile: show_profile(vocoder)
    if not len(wave) or not np.isfinite(wave).all():
        raise RuntimeError("Audio invalide")
    rms, peak = float(np.sqrt(np.mean(wave**2))),float(np.max(np.abs(wave)))
    print(f"RMS={rms:.5f} peak={peak:.5f}")
    if peak < .001:
        raise RuntimeError("Audio presque silencieux : résultat non validé")
    output=Path(a.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    sf.write(output,np.clip(wave,-1,1),44100,subtype="PCM_16")
    print("Fichier WAV :", output)


if __name__ == "__main__":
    main()
