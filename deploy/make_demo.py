"""Create original synthetic fixtures. No third-party media is used."""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1]/'demo';root.mkdir(exist_ok=True)
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=size=1280x720:rate=24','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','8','-c:v','libx264','-preset','ultrafast','-crf','30','-c:a','aac','-b:a','96k','-movflags','+faststart',str(root/'demo.mp4')],check=True)
for height in [360,720]:
    folder=root/f'hls{height}';folder.mkdir(exist_ok=True)
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(root/'demo.mp4'),'-vf',f'scale=-2:{height}','-c:v','libx264','-preset','ultrafast','-crf','30','-c:a','aac','-hls_time','2','-hls_list_size','0','-hls_segment_filename',str(folder/'segment%03d.ts'),str(folder/'index.m3u8')],check=True)
(root/'master.m3u8').write_text('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=600000,RESOLUTION=640x360\nhls360/index.m3u8\n#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720\nhls720/index.m3u8\n')
(root/'protected.mpd').write_text('<?xml version="1.0"?><MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static"><Period><AdaptationSet mimeType="video/mp4"><ContentProtection schemeIdUri="urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed"/><Representation id="test" height="720" bandwidth="2000000"/></AdaptationSet></Period></MPD>')
(root/'demo.vtt').write_text('WEBVTT\n\n00:00:00.000 --> 00:00:08.000\nStreamForge owned-media test fixture\n')
print('Created MP4, two-quality HLS, subtitle and protection-inspection fixtures.')
