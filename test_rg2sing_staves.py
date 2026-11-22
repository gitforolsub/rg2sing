#!/usr/bin/env python3
import unittest
from rg2sing_staves import split_staff_model

def note(t,p,up):
 return {'tick':t,'duration':480,'type':'note','index':0,'properties':{'pitch':str(p),'NoteStemUp':str(up).lower()}}
def lyric(t,s):
 return {'tick':t,'duration':0,'type':'text','index':1,'properties':{'type':'lyric','text':s}}
def seg(name,track,events):
 return {'part':name,'track_id':track,'iteration':0,'events':events}

class Tests(unittest.TestCase):
 def setUp(self):
  self.model={'tempo':[(0,120.0)],'segments':[
   seg('Alti',1,[lyric(-960,'Glo'),note(-960,64,True),note(-960,60,False),lyric(-480,'ria'),note(-480,65,True),note(-480,62,False)]),
   seg('Tenors/Basses',2,[lyric(-960,'Glo'),note(-960,52,True),note(-960,43,False),lyric(-480,'ria'),note(-480,55,True),note(-480,45,False)])]}
 def test_mapping_and_pickup(self):
  score,diag=split_staff_model(self.model)
  self.assertEqual(diag['negative_tick_shift'],960)
  self.assertEqual(diag['note_counts'],dict(zip(('Soprani','Alti','Tenors','Basses'),(2,2,2,2))))
  self.assertEqual(score['tempo'][0][0],0)
  for part,pitches in [('Soprani',[64,65]),('Alti',[60,62]),('Tenors',[52,55]),('Basses',[43,45])]:
   values=[e for s in score['segments'] if s['part']==part for e in s['events'] if e['type']=='note']
   self.assertEqual([int(x['properties']['pitch']) for x in values],pitches)
   self.assertEqual([x['tick'] for x in values],[0,480])
 def test_named_voices_shared_two_tracks(self):
  m={'tempo':[(0,120.0)],'segments':[
   seg('Soprani',0,[note(-960,64,True),note(-960,67,True)]),
   seg('Alti',0,[note(-960,60,False),note(-960,64,False)]),
   seg('Ténors',2,[note(-960,55,True),note(-960,55,True)]),
   seg('Basses',2,[note(-960,48,False),note(-960,48,False)])]}
  out,diag=split_staff_model(m,layout='satb-2staves')
  self.assertEqual(diag['negative_tick_shift'],960)
  self.assertTrue(diag['already_separated'])
  self.assertEqual(diag['note_counts'], {'Soprani':2,'Alti':2,'Tenors':2,'Basses':2})
  self.assertEqual([s['part'] for s in out['segments']], ['Soprani','Alti','Tenors','Basses'])
  self.assertEqual(diag['simultaneous_notes']['Alti']['0'], ['60','64'])
  self.assertEqual(diag['simultaneous_notes']['Tenors']['0'], ['55','55'])

 def test_no_silent_guess(self):
  self.model['segments'][0]['events'][1]['properties'].pop('NoteStemUp')
  with self.assertRaisesRegex(ValueError,'sans NoteStemUp'):
   split_staff_model(self.model)
 def test_four_staves_unchanged(self):
  m={'tempo':[(0,120)],'segments':[seg(p,i,[note(0,60+i,False)]) for i,p in enumerate(('Soprani','Alti','Tenors','Basses'))]}
  out,diag=split_staff_model(m)
  self.assertEqual(diag['layout'],'satb-4staves')
  self.assertEqual([s['part'] for s in out['segments']],['Soprani','Alti','Tenors','Basses'])

if __name__=='__main__':unittest.main()

