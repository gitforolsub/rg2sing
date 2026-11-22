#!/usr/bin/env python3
"""Mix pre-rendered SATB vocal WAV stems into MP3 entirely offline via ffmpeg.
Each source file named Soprani.wav, Alti.wav, Tenors.wav, Basses.wav.
"""
import argparse,pathlib,shutil,subprocess,sys
PARTS=('Soprani','Alti','Tenors','Basses')
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('stem_dir');p.add_argument('--output',default='chant_final.mp3');p.add_argument('--bitrate',default='256k')
 p.add_argument('--allow-missing',action='store_true',help='mix available voices only')
 a=p.parse_args();directory=pathlib.Path(a.stem_dir)
 if not shutil.which('ffmpeg'):p.error('ffmpeg required: sudo apt install ffmpeg')
 found=[directory/(part+'.wav') for part in PARTS if (directory/(part+'.wav')).exists()]
 if len(found)!=4 and not a.allow_missing:p.error('Missing SATB wav stems in '+str(directory))
 if not found:p.error('No wav stems found')
 cmd=['ffmpeg','-nostdin','-hide_banner','-y']
 for file in found:cmd+=['-i',str(file)]
 cmd+=['-filter_complex',f'amix=inputs={len(found)}:duration=longest:normalize=1,alimiter=limit=0.95[a]','-map','[a]','-codec:a','libmp3lame','-b:a',a.bitrate,str(a.output)]
 subprocess.run(cmd,check=True)
 print('Created',a.output)
if __name__=='__main__':main()
