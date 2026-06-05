"""
Telegram Sticker <-> Image Bot
Supports: static stickers (WEBP), animated stickers (TGS/LOTTIE), video stickers (WEBM)
"""

import os
import json
import asyncio
import tempfile
import subprocess
from pathlib import Path
from io import BytesIO

from telegram import Update, InputSticker
from telegram.constants import StickerFormat
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# --- pip install python-telegram-bot[all] Pillow cairosvg lottie-python ---

BOT_TOKEN = os.environ.get("BOT_TOKEN")

print("TOKEN EXISTS:", BOT_TOKEN is not None)
print("TOKEN LENGTH:", len(BOT_TOKEN) if BOT_TOKEN else 0)

# Conversation states
WAITING_FOR_STICKER_NAME = 1
WAITING_FOR_EMOJI        = 2

# ─────────────────────────────────────────────
#  HELPER UTILITIES
# ─────────────────────────────────────────────

def webp_to_png(webp_bytes: bytes) -> bytes:
    """Convert WEBP bytes → PNG bytes using Pillow."""
    from PIL import Image
    img = Image.open(BytesIO(webp_bytes)).convert("RGBA")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def png_to_webp(png_bytes: bytes, size: tuple = (512, 512)) -> bytes:
    """Convert PNG/image bytes → WEBP sticker bytes (512×512)."""
    from PIL import Image
    img = Image.open(BytesIO(png_bytes)).convert("RGBA")
    img.thumbnail(size, Image.LANCZOS)

    # Pad to exactly 512×512 on transparent background
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    offset = ((size[0] - img.width) // 2, (size[1] - img.height) // 2)
    canvas.paste(img, offset, img)

    buf = BytesIO()
    canvas.save(buf, format="WEBP")
    return buf.getvalue()


def tgs_to_gif(tgs_path: str, out_gif: str) -> bool:
    """
    Convert a .tgs (gzipped Lottie JSON) to GIF using lottie-python + Pillow.
    Falls back to ffmpeg if lottie-python is unavailable.
    """
    try:
        import gzip, lottie
        from lottie.exporters import export_gif

        with gzip.open(tgs_path) as f:
            anim = lottie.parsers.tgs.parse_tgs(f)
        export_gif(anim, out_gif, fps=24)
        return True
    except ImportError:
        pass

    # ffmpeg fallback (requires rlottie-python or lottie2gif binary)
    try:
        result = subprocess.run(
            ["lottie2gif", tgs_path, "-o", out_gif],
            capture_output=True, timeout=30
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def webm_to_gif(webm_path: str, out_gif: str) -> bool:
    """Convert .webm video sticker → GIF using ffmpeg."""
    try:
        result = subprocess.run([
            "ffmpeg", "-y", "-i", webm_path,
            "-vf", "fps=15,scale=320:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
            "-loop", "0", out_gif
        ], capture_output=True, timeout=60)
        print("FFMPEG RETURN CODE:", result.returncode)
        print("STDOUT:", result.stdout.decode(errors="ignore"))
        print("STDERR:", result.stderr.decode(errors="ignore"))
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def gif_to_webm(gif_path: str, out_webm: str) -> bool:
    """Convert GIF → .webm (VP9, required format for video stickers)."""
    try:
        result = subprocess.run([
            "ffmpeg", "-y", "-i", gif_path,
            "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "30",
            "-auto-alt-ref", "0",
            "-vf", "scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000",
            out_webm
        ], capture_output=True, timeout=60)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ─────────────────────────────────────────────
#  COMMAND HANDLERS
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Sticker ↔ Image Bot*\n\n"
        "Here's what I can do:\n\n"
        "📥 *Sticker → Image/GIF*\n"
        "  Just send me any sticker!\n"
        "  • Static sticker → PNG\n"
        "  • Animated (.tgs) sticker → GIF\n"
        "  • Video (.webm) sticker → GIF\n\n"
        "📤 *Image → Sticker*\n"
        "  Send me a PNG/JPG/WEBP image → I'll send it back as a sticker\n\n"
        "🎞 *GIF → Video Sticker*\n"
        "  Send me a GIF → I'll convert it to a video sticker\n\n"
        "ℹ️ Use /help for detailed instructions."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*How to use this bot:*\n\n"
        "1️⃣ *Sticker → Image*: Forward or send any sticker\n"
        "2️⃣ *Image → Sticker*: Send a photo (as a file for best quality)\n"
        "3️⃣ *GIF → Video Sticker*: Send a GIF as a document\n\n"
        "*Notes:*\n"
        "• Animated sticker conversion requires `lottie-python` or `lottie2gif` installed on the server\n"
        "• Video sticker conversion requires `ffmpeg`\n"
        "• Max sticker size: 512×512px\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─────────────────────────────────────────────
#  STICKER → IMAGE / GIF
# ─────────────────────────────────────────────

async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sticker = update.message.sticker
    msg = await update.message.reply_text("⏳ Converting sticker…")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Download the sticker file
        file = await sticker.get_file()

        if sticker.is_animated:
            # TGS (Lottie) → GIF
            tgs_path = os.path.join(tmpdir, "sticker.tgs")
            gif_path = os.path.join(tmpdir, "sticker.gif")
            await file.download_to_drive(tgs_path)

            success = tgs_to_gif(tgs_path, gif_path)
            if success and os.path.exists(gif_path):
                await update.message.reply_document(
                    document=open(gif_path, "rb"),
                    filename="animated_sticker.gif",
                    caption="🎞 Animated sticker → GIF"
                )
            else:
                # Fallback: send the raw TGS JSON
                await update.message.reply_document(
                    document=open(tgs_path, "rb"),
                    filename="sticker.tgs",
                    caption=(
                        "⚠️ Could not render GIF on this server "
                        "(needs lottie2gif/ffmpeg). "
                        "Here's the raw .tgs file — open it with a Lottie viewer."
                    )
                )

        elif sticker.is_video:
            # WEBM → GIF
            webm_path = os.path.join(tmpdir, "sticker.webm")
            gif_path  = os.path.join(tmpdir, "sticker.gif")
            await file.download_to_drive(webm_path)

            success = webm_to_gif(webm_path, gif_path)
            if success and os.path.exists(gif_path):
                await update.message.reply_document(
                    document=open(gif_path, "rb"),
                    filename="video_sticker.gif",
                    caption="🎞 Video sticker → GIF"
                )
            else:
                await update.message.reply_document(
                    document=open(webm_path, "rb"),
                    filename="sticker.webm",
                    caption="⚠️ ffmpeg not available. Here's the raw .webm file."
                )

        else:
            # Static WEBP → PNG
            webp_path = os.path.join(tmpdir, "sticker.webp")
            await file.download_to_drive(webp_path)

            png_bytes = webp_to_png(open(webp_path, "rb").read())
            await update.message.reply_document(
                document=BytesIO(png_bytes),
                filename="sticker.png",
                caption="🖼 Static sticker → PNG"
            )

    await msg.delete()


# ─────────────────────────────────────────────
#  IMAGE → STICKER
# ─────────────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles photos sent compressed by Telegram."""
    msg = await update.message.reply_text("⏳ Converting image to sticker…")
    photo = update.message.photo[-1]  # largest size

    with tempfile.TemporaryDirectory() as tmpdir:
        file = await photo.get_file()
        img_path = os.path.join(tmpdir, "image.jpg")
        await file.download_to_drive(img_path)

        webp_bytes = png_to_webp(open(img_path, "rb").read())
        await update.message.reply_sticker(sticker=BytesIO(webp_bytes))

    await msg.delete()


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles images/GIFs sent as documents (uncompressed)."""
    doc = update.message.document
    mime = doc.mime_type or ""

    if mime.startswith("image/gif") or doc.file_name.lower().endswith(".gif"):
        # GIF → Video sticker (WEBM)
        msg = await update.message.reply_text("⏳ Converting GIF to video sticker…")
        with tempfile.TemporaryDirectory() as tmpdir:
            file = await doc.get_file()
            gif_path  = os.path.join(tmpdir, "input.gif")
            webm_path = os.path.join(tmpdir, "output.webm")
            await file.download_to_drive(gif_path)

            success = gif_to_webm(gif_path, webm_path)
            if success and os.path.exists(webm_path):
                await update.message.reply_sticker(sticker=open(webm_path, "rb"))
            else:
                await update.message.reply_text(
                    "⚠️ Could not convert GIF to video sticker. "
                    "Make sure ffmpeg is installed on the server."
                )
        await msg.delete()

    elif mime.startswith("image/") or doc.file_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        # Image → Static sticker
        msg = await update.message.reply_text("⏳ Converting image to sticker…")
        with tempfile.TemporaryDirectory() as tmpdir:
            file = await doc.get_file()
            img_path = os.path.join(tmpdir, "image")
            await file.download_to_drive(img_path)

            webp_bytes = png_to_webp(open(img_path, "rb").read())
            await update.message.reply_sticker(sticker=BytesIO(webp_bytes))
        await msg.delete()

    else:
        await update.message.reply_text(
            "❓ Send me a PNG, JPG, WEBP, or GIF file to convert to a sticker."
        )


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # Sticker → image
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))

    # Image/GIF → sticker
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
