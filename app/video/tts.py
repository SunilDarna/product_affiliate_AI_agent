import os
import asyncio
import edge_tts
from app.config import WORKSPACE_DIR

# Using an energetic Indian-English voice
DEFAULT_VOICE = "en-IN-PrabhatNeural" # Alternative: "en-IN-NeerjaNeural"

async def _generate_tts_and_subtitles(text, output_filename="voiceover"):
    """
    Asynchronous function to generate TTS audio and matching VTT subtitles.
    """
    audio_path = os.path.join(WORKSPACE_DIR, f"{output_filename}.mp3")
    subtitle_path = os.path.join(WORKSPACE_DIR, f"{output_filename}.srt")
    
    # We increase the rate slightly for a fast-paced "Shorts" feel
    communicate = edge_tts.Communicate(text, DEFAULT_VOICE, rate="+15%")
    submaker = edge_tts.SubMaker()
    
    with open(audio_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # Create subtitles perfectly synced with the generated audio
                submaker.feed(chunk)

    with open(subtitle_path, "w", encoding="utf-8") as sub_file:
        sub_file.write(submaker.get_srt())

    print(f"Generated TTS audio: {audio_path}")
    print(f"Generated Subtitles: {subtitle_path}")
    
    return audio_path, subtitle_path

def create_voiceover(text, filename="voiceover"):
    """
    Synchronous wrapper for generating TTS and subtitles.
    Returns a tuple: (audio_path, subtitle_path)
    """
    return asyncio.run(_generate_tts_and_subtitles(text, filename))

if __name__ == "__main__":
    # Test
    test_text = "Wait! Before you buy another smartwatch, you need to see this. The Noise ColorFit Pro 4 is blowing up right now. Click the link in the description to grab yours before it sells out!"
    audio, sub = create_voiceover(test_text, "test_voice")
    print("Audio saved to:", audio)
    print("Subtitles saved to:", sub)
