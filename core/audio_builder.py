import os
import re
import requests
import asyncio
import numpy as np
from dotenv import load_dotenv

load_dotenv()

# ===========================================================================
# Voice Design Prompt for "語昕" — The Good Morning Vietnam host
# Used by VoxCPM2 only (natural-language voice design in parentheses)
# ===========================================================================
YUXIN_VOICE_DESIGN = (
    "(A professional Chinese-speaking female news anchor in her early 30s. "
    "Warm, confident, and authoritative voice with clear diction. "
    "Energetic yet measured pace, speaking fluent Mandarin.)"
)

# Kokoro voice for "語昕" — Mandarin female style
# Depending on Kokoro version, 'zf_xiaoxiao' or 'zf_xiaoni' are common for Mandarin female
KOKORO_VOICE = os.environ.get("KOKORO_VOICE", "zf_xiaoxiao")


# ===========================================================================
# Helper: split long scripts into sentence-boundary chunks (for VoxCPM2)
# ===========================================================================
def _split_into_chunks(text: str, max_chars: int = 500) -> list:
    """
    Split text into chunks at sentence boundaries so VoxCPM2 produces
    natural-sounding audio without cutoffs.
    """
    # 針對中文的標點符號進行切分
    sentences = re.split(r'(?<=[。！？!?])\s*', text.strip())
    chunks = []
    current = ""
    for sentence in sentences:
        if not sentence: continue
        if len(sentence) > max_chars:
            sub_parts = re.split(r'(?<=[，、,])\s*', sentence)
            for part in sub_parts:
                if len(current) + len(part) <= max_chars:
                    current = (current + part) if current else part
                else:
                    if current:
                        chunks.append(current)
                    current = part
        elif len(current) + len(sentence) <= max_chars:
            current = (current + sentence) if current else sentence
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


# ===========================================================================
# TTS Option 1: ElevenLabs (Premium paid API)
# ===========================================================================
def generate_audio_elevenlabs(script_text, output_file):
    """
    如果您在 .env 填寫了 ELEVENLABS_API_KEY，就會呼叫好萊塢級語音
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key or api_key == "your_elevenlabs_api_key_here":
        return False

    print("\n[Audio] ElevenLabs API Key detected — calling premium voice synthesis...")
    url = "https://api.elevenlabs.io/v1/text-to-speech/pNInz6obpgDQGcFmaJgB"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }
    data = {
        "text": script_text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.7,
            "style": 0.06,
            "use_speaker_boost": True
        }
    }

    response = requests.post(url, json=data, headers=headers)
    if response.status_code == 200:
        with open(output_file, 'wb') as f:
            f.write(response.content)
        return True
    else:
        print(f"ElevenLabs 錯誤: {response.text}")
        return False


# ===========================================================================
# TTS Option 2: VoxCPM2 (Open-source — local GPU only)
# Enable via: USE_VOXCPM=true in .env
# NOT suitable for GitHub Actions (requires GPU + large model download)
# ===========================================================================
def generate_audio_voxcpm(script_text, output_file):
    use_voxcpm = os.environ.get("USE_VOXCPM", "").strip().lower() in ("1", "true", "yes")
    if not use_voxcpm:
        return False

    try:
        from voxcpm import VoxCPM
        import soundfile as sf
        import torch
    except ImportError as e:
        print(f"\n[Audio] ⚠️  VoxCPM2 not installed ({e}).")
        print("       Run: pip install voxcpm soundfile torch")
        return False

    print("\n[Audio] 🎤 VoxCPM2 enabled — generating premium open-source TTS...")

    try:
        if torch.cuda.is_available():
            device = "cuda"
            print(f"  ✔️  GPU detected: {torch.cuda.get_device_name(0)}")
        else:
            device = "cpu"
            print("  ⚠️  No GPU detected. Running VoxCPM2 on CPU (may be slow).")

        print("  Loading VoxCPM2 model (first run auto-downloads from Hugging Face)...")
        model = VoxCPM.from_pretrained("openbmb/VoxCPM2", device=device)
        sample_rate = model.tts_model.sample_rate

        chunks = _split_into_chunks(script_text, max_chars=300)
        print(f"  Script split into {len(chunks)} chunks for chunked inference.")

        all_audio = []
        for i, chunk in enumerate(chunks, 1):
            text_with_voice = f"{YUXIN_VOICE_DESIGN} {chunk}" if i == 1 else chunk
            print(f"  [VoxCPM2] Chunk {i}/{len(chunks)}: {chunk[:30]}...")
            wav = model.generate(
                text=text_with_voice,
                cfg_value=2.0,
                inference_timesteps=10
            )
            all_audio.append(wav)

        combined_audio = np.concatenate(all_audio)
        print(f"  ✔️  Total audio: {len(combined_audio) / sample_rate:.1f}s")

        wav_file = output_file.replace(".mp3", "_voxcpm_raw.wav")
        import soundfile as sf
        sf.write(wav_file, combined_audio, sample_rate)

        from pydub import AudioSegment
        sound = AudioSegment.from_wav(wav_file)
        sound.export(output_file, format="mp3", bitrate="192k")

        if os.path.exists(wav_file):
            os.remove(wav_file)

        print(f"  ✔️  VoxCPM2 audio ready: {output_file}")
        return True

    except Exception as e:
        print(f"\n  ❌ VoxCPM2 generation failed: {e}")
        return False


# ===========================================================================
# TTS Option 3: Kokoro TTS (Open-source — CPU-friendly, GitHub Actions ready)
# Install: pip install kokoro>=0.9.4
# ===========================================================================
def generate_audio_kokoro(script_text, output_file):
    try:
        from kokoro import KPipeline
        import soundfile as sf
    except ImportError:
        return False

    print(f"\n[Audio] 🎙️  Kokoro TTS — generating high-quality CPU audio (voice: {KOKORO_VOICE})...")

    try:
        # z for Mandarin/Chinese
        lang_code = 'z'
        pipeline = KPipeline(lang_code=lang_code)

        all_audio = []
        total_chunks = 0
        print("  Processing script...")

        for graphemes, phonemes, audio in pipeline(
            script_text,
            voice=KOKORO_VOICE,
            speed=1.05
        ):
            all_audio.append(audio)
            total_chunks += 1

        if not all_audio:
            print("  ❌ Kokoro generated no audio chunks.")
            return False

        combined = np.concatenate(all_audio)
        duration = len(combined) / 24000
        print(f"  ✔️  {total_chunks} chunks generated. Total: {duration:.1f}s ({duration/60:.1f} min)")

        wav_file = output_file.replace(".mp3", "_kokoro_raw.wav")
        sf.write(wav_file, combined, 24000)

        from pydub import AudioSegment
        sound = AudioSegment.from_wav(wav_file)
        sound.export(output_file, format="mp3", bitrate="192k")

        if os.path.exists(wav_file):
            os.remove(wav_file)

        print(f"  ✔️  Kokoro MP3 ready: {output_file}")
        return True

    except Exception as e:
        print(f"  ❌ Kokoro TTS failed: {e}")
        print("     Falling back to Edge TTS...")
        return False


# ===========================================================================
# TTS Option 4: Edge TTS (Ultimate fallback — free, Microsoft Azure Neural)
# ===========================================================================
async def generate_audio_edge(script_text, output_file):
    print("\n[Audio] 正在使用 Microsoft Azure 神經網路語音 (Edge TTS)...")
    import edge_tts
    # 選擇台灣專業女聲
    voice = "zh-TW-HsiaoChenNeural" 
    communicate = edge_tts.Communicate(script_text, voice, rate="+5%")
    await communicate.save(output_file)
    return True


# ===========================================================================
# Main pipeline entry point
# Priority: ElevenLabs → VoxCPM2 → Kokoro TTS → Edge TTS
# ===========================================================================
def build_podcast_audio(script_file="script.txt", output_file="podcast.mp3"):
    if not os.path.exists(script_file):
        print(f"找不到講稿: {script_file}")
        return

    try:
        with open(script_file, "r", encoding="utf-8-sig") as f:
            script_text = f.read()
    except UnicodeDecodeError:
        with open(script_file, "r", encoding="mbcs") as f:
            script_text = f.read()

    # 清理講稿
    import re
    script_text = re.sub(r'\[.*?\]', '', script_text)
    script_text = re.sub(r'\(.*?\)', '', script_text)
    script_text = script_text.replace('*', '')
    script_text = script_text.replace('#', '')
    script_text = script_text.replace('_', '')
    script_text = script_text.replace('---', ' ')
    script_text = re.sub(r'\n{3,}', '\n\n', script_text)

    print("\n[Audio] TTS Priority: ElevenLabs → VoxCPM2 (local GPU) → Kokoro → Edge TTS")

    success = generate_audio_elevenlabs(script_text, output_file)

    if not success:
        success = generate_audio_voxcpm(script_text, output_file)

    if not success:
        success = generate_audio_kokoro(script_text, output_file)

    if not success:
        try:
            asyncio.run(generate_audio_edge(script_text, output_file))
            success = True
        except Exception as e:
            print(f"\n❌ Error generating Edge TTS audio: {e}")
            print("Please ensure edge-tts is installed: pip install edge-tts")
            return

    if success:
        print(f"\n🎧 廣播生成大功告成！檔案已儲存為：{output_file}")


if __name__ == "__main__":
    build_podcast_audio()
