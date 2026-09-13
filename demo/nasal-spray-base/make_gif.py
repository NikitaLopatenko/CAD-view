from pathlib import Path
import subprocess
import imageio_ffmpeg

root = Path(__file__).resolve().parent
mp4 = root / "cadview-nasal-spray-demo.mp4"
gif = root / "gallery" / "cadview-nasal-spray-demo.gif"
ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

cmd = [
    ffmpeg,
    "-y",
    "-i",
    str(mp4),
    "-vf",
    "fps=6,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4",
    "-loop",
    "0",
    str(gif),
]
subprocess.run(cmd, check=True)
print("gif_bytes", gif.stat().st_size)
