#!/usr/bin/env python3
"""Séparation conservatrice des deux portées SATB grâce à NoteStemUp.

Ne devine jamais la voix d'une note dont le sens de hampe manque.
Les paroles d'une portée sont partagées aux deux voix pour analyse et doivent
être vérifiées si la partition porte des textes distincts pour chaque voix.
"""
from __future__ import annotations
import collections
import copy

VOICE_ORDER = ('Soprani', 'Alti', 'Tenors', 'Basses')

def stem_up(event):
    val = event.get('properties', {}).get('NoteStemUp')
    if isinstance(val, bool):
        return val
    if isinstance(val, str) and val.lower() in ('true', 'false', '1', '0'):
        return val.lower() in ('true', '1')
    return None

def split_staff_model(model, layout='auto', upper_staff=None, lower_staff=None):
    """Retourne (modèle_normalisé, diagnostic), sans modifier le modèle d'entrée."""
    source = copy.deepcopy(model)
    bypart = collections.defaultdict(list)
    for seg in source['segments']:
        if any(e['type'] == 'note' for e in seg['events']):
            bypart[seg['part']].append(seg)
    parts = list(bypart)
    tracks = {part: sorted({seg['track_id'] for seg in segments})
              for part, segments in bypart.items()}
    named_four = set(VOICE_ORDER).issubset(parts) or (
        {'Soprani', 'Alti', 'Ténors', 'Basses'}.issubset(parts))
    # Rosegarden may put two named voice parts on the same graphical track.
    # Four named parts on two track IDs need no stem-based split.
    two_tracks_named = named_four and len({t for ids in tracks.values() for t in ids}) == 2
    if layout == 'auto':
        if two_tracks_named:
            layout = 'satb-2staves'
        elif len(parts) == 2 and not {'Soprani', 'Alti', 'Tenors', 'Basses'}.issubset(parts):
            layout = 'satb-2staves'
        elif len(parts) >= 4 and set(VOICE_ORDER).issubset(parts):
            layout = 'satb-4staves'
        else:
            raise ValueError(f"Disposition indéterminée ({parts}). Choisir --layout satb-2staves et éventuellement --upper-staff/--lower-staff.")
    if layout not in ('satb-2staves','satb-4staves'):
        raise ValueError(f'Disposition inconnue : {layout}')
    diag = {'layout': layout, 'source_parts': parts, 'staff_mapping': {}, 'stem_missing': [],
            'lyric_assumptions': [], 'negative_tick_shift': 0, 'note_counts': {}}
    if layout == 'satb-2staves' and two_tracks_named:
        # The XML has four logical parts already, even though there are only
        # two physical tracks. Preserve all notes and chords unchanged.
        normalized = {'Ténors': 'Tenors'}
        for seg in source['segments']:
            seg['part'] = normalized.get(seg['part'], seg['part'])
        diag['staff_mapping'] = {
            'upper': {'track_id': tracks['Soprani'][0], 'up': 'Soprani', 'down': 'Alti'},
            'lower': {'track_id': tracks.get('Tenors', tracks.get('Ténors'))[0],
                      'up': 'Tenors', 'down': 'Basses'},
        }
        diag['already_separated'] = True
    elif layout == 'satb-2staves':
        if len(parts) != 2:
            raise ValueError(f'Il faut exactement deux portées avec des notes, trouvé {parts}')
        # Track order is more stable than part name for staff order.
        if upper_staff is None or lower_staff is None:
            track_order = sorted(parts, key=lambda p: min(s['track_id'] for s in bypart[p]))
            upper_staff = upper_staff or track_order[0]
            lower_staff = lower_staff or track_order[1]
        if upper_staff == lower_staff or set((upper_staff,lower_staff)) != set(parts):
            raise ValueError(f'Sélection de portées invalide: {upper_staff!r}, {lower_staff!r}; disponibles: {parts}')
        mapping = {upper_staff: ('Soprani','Alti'), lower_staff: ('Tenors','Basses')}
        diag['staff_mapping'] = {p: {'up':v[0], 'down':v[1]} for p,v in mapping.items()}
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
                        diag['stem_missing'].append({'staff': seg['part'], 'tick': ev['tick'],
                                                     'pitch': ev.get('properties',{}).get('pitch')})
                    else:
                        streams[up_part if up else down_part].append(copy.deepcopy(ev))
                elif ev['type'] == 'text' and ev.get('properties',{}).get('type') == 'lyric':
                    # Rosegarden text may be attached to the staff rather than a voice.
                    for key in streams:
                        streams[key].append(copy.deepcopy(ev))
                    diag['lyric_assumptions'].append({'staff':seg['part'],'tick':ev['tick'],
                        'text':ev.get('properties',{}).get('text',''), 'method':'copied_to_both_voices'})
            for target, events in streams.items():
                if events:
                    new = dict(seg)
                    new['part'] = target
                    new['events'] = events
                    out.append(new)
        if diag['stem_missing']:
            first=diag['stem_missing'][:5]
            raise ValueError(f"{len(diag['stem_missing'])} notes sans NoteStemUp explicite ; classement impossible sans risque. Exemples: {first}")
        source['segments'] = out
    else:
        diag['staff_mapping'] = {p:{'as':p} for p in parts}
    # Keep all temporal relations and move a possible pickup to zero.
    earliest = min((e['tick'] for s in source['segments'] for e in s['events'] if e['type']=='note'), default=0)
    if earliest < 0:
        shift=-earliest
        for seg in source['segments']:
            for e in seg['events']:
                e['tick']+=shift
        tempos=source['tempo']
        source['tempo']=sorted(set([(0,tempos[0][1])] + [(max(0,t+shift),bpm) for t,bpm in tempos]))
        diag['negative_tick_shift']=shift
    # Diagnostic only: concurrent pitches within a logical part are NOT
    # necessarily duplicates and must not be discarded here.
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
    diag['note_counts']={p:sum(e['type']=='note' for s in source['segments'] if s['part']==p for e in s['events']) for p in VOICE_ORDER}
    return source,diag
