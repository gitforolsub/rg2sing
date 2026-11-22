#!/usr/bin/env python3
"""Identification SATB par noms logiques ou séparation prudente par hampes.

Les noms S/A/T/B sont des voix, indépendamment du numéro des pistes
Rosegarden. Seules deux pistes réellement combinées requièrent NoteStemUp.
"""
from __future__ import annotations
import collections
import copy

VOICE_ORDER = ('Soprani', 'Alti', 'Tenors', 'Basses')
VOICE_NAMES = {
    'S': 'Soprani', 'A': 'Alti', 'T': 'Tenors', 'B': 'Basses',
    'Soprani': 'Soprani', 'Alti': 'Alti', 'Tenors': 'Tenors',
    'Ténors': 'Tenors', 'Basses': 'Basses',
}


def stem_up(event):
    val = event.get('properties', {}).get('NoteStemUp')
    if isinstance(val, bool):
        return val
    if isinstance(val, str) and val.lower() in ('true', 'false', '1', '0'):
        return val.lower() in ('true', '1')
    return None


def split_staff_model(model, layout='auto', upper_staff=None, lower_staff=None):
    """Retourne (modèle_normalisé, diagnostic), sans modifier le modèle d'entrée.

    Les quatre voix explicitement nommées sont conservées même lorsque leurs
    track_id sont non contigus, ou distincts sur seulement deux portées.
    """
    source = copy.deepcopy(model)
    bypart = collections.defaultdict(list)
    for seg in source['segments']:
        if any(e['type'] == 'note' for e in seg['events']):
            bypart[seg['part']].append(seg)
    parts = list(bypart)
    tracks = {part: sorted({seg['track_id'] for seg in segments})
              for part, segments in bypart.items()}
    normalized_parts = {p: VOICE_NAMES.get(p) for p in parts}
    named_four = (len(parts) == 4 and
                  set(normalized_parts.values()) == set(VOICE_ORDER) and
                  None not in normalized_parts.values())
    distinct_tracks = {t for ids in tracks.values() for t in ids}
    two_tracks_named = named_four and len(distinct_tracks) == 2
    if layout == 'auto':
        if named_four:
            layout = 'satb-2staves' if two_tracks_named else 'satb-4staves'
        elif len(parts) == 2:
            layout = 'satb-2staves'
        else:
            raise ValueError(
                f'Disposition indéterminée ({parts}). '
                'Nommer explicitement S, A, T, B (ou les noms SATB complets), '
                'ou fournir deux portées combinées pour --layout satb-2staves.'
            )
    if layout not in ('satb-2staves', 'satb-4staves'):
        raise ValueError(f'Disposition inconnue : {layout}')
    diag = {'layout': layout, 'source_parts': parts, 'staff_mapping': {},
            'stem_missing': [], 'lyric_assumptions': [],
            'negative_tick_shift': 0, 'note_counts': {}}

    if named_four:
        # Ne pas redistribuer par hampes des voix déjà identifiées. Un track_id
        # est une information physique, non une preuve de la voix chantée.
        for seg in source['segments']:
            if seg['part'] in VOICE_NAMES:
                seg['part'] = VOICE_NAMES[seg['part']]
        diag['staff_mapping'] = {
            p: {'as': normalized_parts[p], 'track_ids': tracks[p]}
            for p in parts
        }
        diag['already_separated'] = True
        diag['track_count'] = len(distinct_tracks)
        if two_tracks_named:
            # Maintient le diagnostic historique des deux pistes partagées.
            reverse = {normalized_parts[p]: p for p in parts}
            diag['staff_mapping'] = {
                'upper': {'track_id': tracks[reverse['Soprani']][0],
                          'up': 'Soprani', 'down': 'Alti'},
                'lower': {'track_id': tracks[reverse['Tenors']][0],
                          'up': 'Tenors', 'down': 'Basses'},
            }
    elif layout == 'satb-2staves':
        if len(parts) != 2:
            raise ValueError(f'Il faut exactement deux portées avec des notes, trouvé {parts}')
        if upper_staff is None or lower_staff is None:
            track_order = sorted(parts, key=lambda p: min(s['track_id'] for s in bypart[p]))
            upper_staff = upper_staff or track_order[0]
            lower_staff = lower_staff or track_order[1]
        if upper_staff == lower_staff or set((upper_staff, lower_staff)) != set(parts):
            raise ValueError(f'Sélection de portées invalide: {upper_staff!r}, {lower_staff!r}; disponibles: {parts}')
        mapping = {upper_staff: ('Soprani', 'Alti'), lower_staff: ('Tenors', 'Basses')}
        diag['staff_mapping'] = {p: {'up': v[0], 'down': v[1]} for p, v in mapping.items()}
        out = []
        for seg in source['segments']:
            if seg['part'] not in mapping:
                continue
            up_part, down_part = mapping[seg['part']]
            streams = {up_part: [], down_part: []}
            for ev in seg['events']:
                if ev['type'] == 'note':
                    up = stem_up(ev)
                    if up is None:
                        diag['stem_missing'].append({
                            'staff': seg['part'], 'tick': ev['tick'],
                            'pitch': ev.get('properties', {}).get('pitch')})
                    else:
                        streams[up_part if up else down_part].append(copy.deepcopy(ev))
                elif ev['type'] == 'text' and ev.get('properties', {}).get('type') == 'lyric':
                    for key in streams:
                        streams[key].append(copy.deepcopy(ev))
                    diag['lyric_assumptions'].append({
                        'staff': seg['part'], 'tick': ev['tick'],
                        'text': ev.get('properties', {}).get('text', ''),
                        'method': 'copied_to_both_voices'})
            for target, events in streams.items():
                if events:
                    new = dict(seg)
                    new['part'] = target
                    new['events'] = events
                    out.append(new)
        if diag['stem_missing']:
            first = diag['stem_missing'][:5]
            raise ValueError(f"{len(diag['stem_missing'])} notes sans NoteStemUp explicite ; classement impossible sans risque. Exemples: {first}")
        source['segments'] = out
    else:
        raise ValueError(f'Quatre voix SATB nommées attendues pour {layout} ; trouvé {parts}')

    earliest = min((e['tick'] for s in source['segments'] for e in s['events']
                    if e['type'] == 'note'), default=0)
    if earliest < 0:
        shift = -earliest
        for seg in source['segments']:
            for e in seg['events']:
                e['tick'] += shift
        tempos = source['tempo']
        source['tempo'] = sorted(set([(0, tempos[0][1])] +
                                    [(max(0, t + shift), bpm) for t, bpm in tempos]))
        diag['negative_tick_shift'] = shift
    simultaneous = {}
    for part in VOICE_ORDER:
        bytick = collections.defaultdict(list)
        for seg in source['segments']:
            if seg['part'] == part:
                for ev in seg['events']:
                    if ev['type'] == 'note':
                        bytick[ev['tick']].append(ev.get('properties', {}).get('pitch'))
        multi = {str(t): pitches for t, pitches in bytick.items() if len(pitches) > 1}
        if multi:
            simultaneous[part] = multi
    diag['simultaneous_notes'] = simultaneous
    diag['note_counts'] = {
        p: sum(e['type'] == 'note' for s in source['segments'] if s['part'] == p
               for e in s['events']) for p in VOICE_ORDER}
    return source, diag
