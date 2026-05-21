import os
import ffmpeg

def strip_audio(input_path, output_path=None):
    """
    Removes the audio track from the given video file.
    Returns the path to the silent video.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Video file not found: {input_path}")
        
    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_silent{ext}"
        
    try:
        print(f"Stripping audio from: {input_path}")
        # Input video
        vid = ffmpeg.input(input_path)
        
        # Output mapping only video (vcodec='copy' is fast since it just remuxes)
        stream = ffmpeg.output(vid.video, output_path, vcodec='copy')
        
        # Run the command, overwrite if exists
        ffmpeg.run(stream, overwrite_output=True, quiet=True)
        
        print(f"Saved silent video to: {output_path}")
        return output_path
    except ffmpeg.Error as e:
        error_msg = e.stderr.decode('utf8') if e.stderr else str(e)
        print(f"ffmpeg error during audio strip: {error_msg}")
        return None
