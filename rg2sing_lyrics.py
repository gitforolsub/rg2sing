#!/usr/bin/env python3
"""Alignement monotone des syllabes SATB sur des notes de rythmes distincts.

La notation à deux portées possède souvent un seul flux de paroles (soprano)
et des durées différentes pour A/T/B. L'égalité des instants n'est PAS
une condition pour partager une syllabe. Tout manque réel est diagnostiqué.
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
                # Très gros déplacements : pénalité progressive pour détecter
                # une partition non alignable (ne pas déplacer sur des mesures).
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
