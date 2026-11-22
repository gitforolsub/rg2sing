#!/usr/bin/env python3
"""Alignement monotone des syllabes SATB et contractions de mots chantés.

Une contraction n'est validée que si des syllabes contiguës d'un même mot
se placent sur une seule note cible dont l'intervalle les contient.
"""


def align_lyrics(reference, target, *, step_ticks=480, extra_cost=2.75,
                 missing_cost=30.0):
    """Return (attributions, diagnostics).

    attributions[j] est l'indice d'une note de reference, ou None lorsqu'une
    note de target constitue une prolongation sans nouvelle syllabe.
    La programmation dynamique conserve les syllabes dans leur ordre.
    """
    n, m = len(reference), len(target)
    infinity = float('inf')
    cost = [[infinity]*(m+1) for _ in range(n+1)]
    back = [[None]*(m+1) for _ in range(n+1)]
    cost[0][0]=0.0
    for i in range(n+1):
        for j in range(m+1):
            c=cost[i][j]
            if c==infinity:continue
            if i<n and j<m:
                delta=abs(reference[i]['tick']-target[j]['tick'])/step_ticks
                score=c + delta + max(0.0, delta-4.0)*4.0
                if score<cost[i+1][j+1]:
                    cost[i+1][j+1]=score;back[i+1][j+1]=(i,j,'match')
            if j<m:
                score=c+extra_cost
                if score<cost[i][j+1]:
                    cost[i][j+1]=score;back[i][j+1]=(i,j,'extension')
            if i<n:
                score=c+missing_cost
                if score<cost[i+1][j]:
                    cost[i+1][j]=score;back[i+1][j]=(i,j,'missing')
    assignments=[None]*m
    missing=[];extensions=[];matches=[]
    i,j=n,m
    while i or j:
        step=back[i][j]
        if step is None: raise ValueError('Alignement des paroles impossible')
        pi,pj,operation=step
        if operation=='match':
            assignments[pj]=pi
            matches.append((pi,pj))
        elif operation=='missing':missing.append(pi)
        elif operation=='extension':extensions.append(pj)
        i,j=pi,pj
    matches.reverse(); missing.reverse(); extensions.reverse()
    max_delta=max((abs(reference[a]['tick']-target[b]['tick']) for a,b in matches),default=0)
    return assignments, {'matched':len(matches), 'unassigned_lyrics':missing,
                         'extension_notes':extensions, 'max_tick_offset':max_delta,
                         'score':round(cost[n][m],2)}


def resolve_lyric_contractions(reference, target, assignments, diagnostics):
    """Resolve only unassigned suffix syllables covered by a matched target note.

    Returns (contractions_by_target_index, updated_diagnostics). No input is
    mutated. Each entry specifies a joined syllable and its source indices.
    The caller must regenerate phonemes for the joined word: copying phonemes
    from the initial syllable would truncate the sung word.
    """
    missing = list(diagnostics.get('unassigned_lyrics', []))
    source_to_target = {src: dest for dest, src in enumerate(assignments)
                        if src is not None}
    groups = {}  # target index -> indices of reference syllables
    remaining = []

    for src in missing:
        prev_idx = src - 1
        dest = source_to_target.get(prev_idx)
        if dest is None or src >= len(reference) or prev_idx < 0:
            remaining.append(src)
            continue
        previous, current = reference[prev_idx], reference[src]
        note = target[dest]
        # An explicit Rosegarden trailing hyphen marks a continued word.
        # An adjacent onset alone never authorizes merging distinct words.
        if not previous.get('word_continues', False):
            remaining.append(src)
            continue
        if not previous.get('syllable') or not current.get('syllable'):
            remaining.append(src)
            continue
        if str(current['syllable']).strip() in ('+', '-', '_'):
            remaining.append(src)
            continue
        try:
            preceding_end = int(previous['end_tick'])
            current_start = int(current['tick'])
            current_end = int(current['end_tick'])
            target_start = int(note['tick'])
            target_end = int(note['end'])
        except (KeyError, TypeError, ValueError):
            remaining.append(src)
            continue
        if not (preceding_end == current_start and
                target_start <= int(previous['tick']) < current_start and
                current_end <= target_end):
            remaining.append(src)
            continue
        # Do not contract across another already matched note in this voice.
        if any(src0 is not None and prev_idx < src0 < src
               for src0 in assignments):
            remaining.append(src)
            continue
        if dest not in groups:
            groups[dest] = [prev_idx]
        elif groups[dest][-1] != prev_idx:
            remaining.append(src)
            continue
        groups[dest].append(src)
        source_to_target[src] = dest

    contractions = {}
    for dest, source_indices in sorted(groups.items()):
        syllable = ''.join(str(reference[i]['syllable']) for i in source_indices)
        contractions[dest] = {
            'syllable': syllable,
            'word_continues': bool(reference[source_indices[-1]].get('word_continues', False)),
            'source_indices': source_indices,
        }
    updated = dict(diagnostics)
    updated['unassigned_lyrics'] = remaining
    updated['contracted_lyrics'] = [
        {'target_tick': int(target[dest]['tick']),
         'source_ticks': [int(reference[i]['tick']) for i in item['source_indices']],
         'source_syllables': [reference[i]['syllable'] for i in item['source_indices']],
         'merged_syllable': item['syllable']}
        for dest, item in sorted(contractions.items())
    ]
    return contractions, updated
