"""
HanumanAI Demo Video Creator
Creates an MP4 video from the recorded demo screenshots with a 10-second countdown intro.
"""

import os
import glob
from PIL import Image, ImageDraw, ImageFont
import imageio

# Configuration
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "HanumanAI_Demo.mp4")
FPS = 2  # 2 frames per second for slideshow effect (each frame shown for 0.5s)
COUNTDOWN_FPS = 1  # 1 frame per second for countdown
TARGET_WIDTH = 1280
TARGET_HEIGHT = 800

# Paths
BRAIN_DIR = r"C:\Users\Jatin Mahar\.gemini\antigravity-ide\brain\5523c8cd-0b7d-4713-a76b-47fd500601ff"
CLICK_FEEDBACK_DIR = os.path.join(BRAIN_DIR, ".system_generated", "click_feedback")

# Named screenshots (in order of the demo)
# NOTE: welcome_screen was a Chrome Web Store page, excluded from demo
NAMED_SCREENSHOTS = []

def get_sorted_screenshots():
    """Get all screenshots sorted by timestamp."""
    screenshots = []
    
    # Add named screenshots first (welcome screen)
    for path in NAMED_SCREENSHOTS:
        if os.path.exists(path):
            screenshots.append(path)
    
    # Add click feedback screenshots (sorted by timestamp in filename)
    feedback_files = glob.glob(os.path.join(CLICK_FEEDBACK_DIR, "click_feedback_*.png"))
    feedback_files.sort()  # Sort by filename (which contains timestamp)
    screenshots.extend(feedback_files)
    
    # Add final overview screenshot
    final_path = os.path.join(BRAIN_DIR, "final_overview_1786514554227.png")
    if os.path.exists(final_path):
        screenshots.append(final_path)
    
    # Add sidebar collapsed screenshot
    sidebar_path = os.path.join(BRAIN_DIR, "sidebar_collapsed_1786514297958.png")
    # This is already covered by click feedback, skip to avoid duplication
    
    return screenshots

def resize_frame(img, target_w, target_h):
    """Resize image to target dimensions, maintaining aspect ratio with black bars."""
    img_ratio = img.width / img.height
    target_ratio = target_w / target_h
    
    if img_ratio > target_ratio:
        # Image is wider - fit to width
        new_w = target_w
        new_h = int(target_w / img_ratio)
    else:
        # Image is taller - fit to height
        new_h = target_h
        new_w = int(target_h * img_ratio)
    
    img_resized = img.resize((new_w, new_h), Image.LANCZOS)
    
    # Create black background
    canvas = Image.new('RGB', (target_w, target_h), (10, 10, 20))
    
    # Paste centered
    x = (target_w - new_w) // 2
    y = (target_h - new_h) // 2
    canvas.paste(img_resized, (x, y))
    
    return canvas

def create_countdown_frame(number, target_w, target_h):
    """Create a countdown frame with the HanumanAI branding."""
    img = Image.new('RGB', (target_w, target_h), (10, 10, 25))
    draw = ImageDraw.Draw(img)
    
    # Draw a subtle gradient-like effect with circles
    for i in range(5):
        radius = 200 - i * 30
        x_center = target_w // 2
        y_center = target_h // 2
        color = (20 + i * 8, 15 + i * 5, 40 + i * 10)
        draw.ellipse(
            [x_center - radius, y_center - radius, x_center + radius, y_center + radius],
            fill=color
        )
    
    # Try to use a nice font, fallback to default
    try:
        title_font = ImageFont.truetype("arial.ttf", 28)
        countdown_font = ImageFont.truetype("arial.ttf", 120)
        subtitle_font = ImageFont.truetype("arial.ttf", 18)
    except:
        title_font = ImageFont.load_default()
        countdown_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
    
    # Draw title
    title = "🚀 HanumanAI"
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    draw.text(((target_w - title_w) // 2, 180), title, fill=(200, 180, 255), font=title_font)
    
    # Draw subtitle
    subtitle = "Intelligent Agent Platform — Full Demo"
    sub_bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    sub_w = sub_bbox[2] - sub_bbox[0]
    draw.text(((target_w - sub_w) // 2, 220), subtitle, fill=(150, 140, 180), font=subtitle_font)
    
    # Draw countdown number
    num_text = str(number)
    num_bbox = draw.textbbox((0, 0), num_text, font=countdown_font)
    num_w = num_bbox[2] - num_bbox[0]
    num_h = num_bbox[3] - num_bbox[1]
    
    # Glowing circle behind number
    cx, cy = target_w // 2, target_h // 2 + 20
    for r in range(80, 60, -2):
        alpha = int(255 * (80 - r) / 20)
        glow_color = (min(100 + alpha, 255), min(80 + alpha // 2, 200), min(180 + alpha, 255))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=glow_color)
    
    draw.text(((target_w - num_w) // 2, cy - num_h // 2 - 10), num_text, fill=(255, 255, 255), font=countdown_font)
    
    # Draw "Launching in..." text
    launch_text = "Launching in..."
    launch_bbox = draw.textbbox((0, 0), launch_text, font=subtitle_font)
    launch_w = launch_bbox[2] - launch_bbox[0]
    draw.text(((target_w - launch_w) // 2, target_h - 180), launch_text, fill=(150, 140, 180), font=subtitle_font)
    
    # Draw progress bar
    bar_width = 300
    bar_height = 6
    bar_x = (target_w - bar_width) // 2
    bar_y = target_h - 140
    
    # Background bar
    draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], fill=(40, 35, 60))
    
    # Progress (10 - number gives progress from 0 to 10)
    progress = (10 - number) / 10
    fill_width = int(bar_width * progress)
    if fill_width > 0:
        draw.rectangle([bar_x, bar_y, bar_x + fill_width, bar_y + bar_height], fill=(140, 120, 255))
    
    return img

def create_launch_frame(target_w, target_h):
    """Create the 'GO!' launch frame."""
    img = Image.new('RGB', (target_w, target_h), (10, 10, 25))
    draw = ImageDraw.Draw(img)
    
    try:
        go_font = ImageFont.truetype("arial.ttf", 100)
        sub_font = ImageFont.truetype("arial.ttf", 24)
    except:
        go_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()
    
    # Bright glow
    cx, cy = target_w // 2, target_h // 2
    for r in range(100, 50, -2):
        glow = int(255 * (100 - r) / 50)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(min(80 + glow, 255), min(200 + glow//2, 255), min(100 + glow, 255)))
    
    go_text = "GO!"
    go_bbox = draw.textbbox((0, 0), go_text, font=go_font)
    go_w = go_bbox[2] - go_bbox[0]
    go_h = go_bbox[3] - go_bbox[1]
    draw.text(((target_w - go_w) // 2, cy - go_h // 2 - 10), go_text, fill=(255, 255, 255), font=go_font)
    
    sub_text = "🚀 HanumanAI is launching..."
    sub_bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
    sub_w = sub_bbox[2] - sub_bbox[0]
    draw.text(((target_w - sub_w) // 2, cy + 70), sub_text, fill=(180, 255, 180), font=sub_font)
    
    return img

def create_section_frame(title, subtitle, target_w, target_h):
    """Create a section title frame."""
    img = Image.new('RGB', (target_w, target_h), (15, 12, 30))
    draw = ImageDraw.Draw(img)
    
    try:
        title_font = ImageFont.truetype("arial.ttf", 36)
        sub_font = ImageFont.truetype("arial.ttf", 18)
    except:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()
    
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    draw.text(((target_w - title_w) // 2, target_h // 2 - 30), title, fill=(200, 180, 255), font=title_font)
    
    sub_bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
    sub_w = sub_bbox[2] - sub_bbox[0]
    draw.text(((target_w - sub_w) // 2, target_h // 2 + 20), subtitle, fill=(140, 130, 170), font=sub_font)
    
    return img

def create_end_frame(target_w, target_h):
    """Create end screen."""
    img = Image.new('RGB', (target_w, target_h), (10, 10, 25))
    draw = ImageDraw.Draw(img)
    
    try:
        title_font = ImageFont.truetype("arial.ttf", 40)
        sub_font = ImageFont.truetype("arial.ttf", 20)
    except:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()
    
    title = "HanumanAI"
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    draw.text(((target_w - title_w) // 2, target_h // 2 - 60), title, fill=(200, 180, 255), font=title_font)
    
    sub = "Intelligent Agent Platform"
    sub_bbox = draw.textbbox((0, 0), sub, font=sub_font)
    sub_w = sub_bbox[2] - sub_bbox[0]
    draw.text(((target_w - sub_w) // 2, target_h // 2), sub, fill=(150, 140, 180), font=sub_font)
    
    sub2 = "Demo Complete - Thank You!"
    sub2_bbox = draw.textbbox((0, 0), sub2, font=sub_font)
    sub2_w = sub2_bbox[2] - sub2_bbox[0]
    draw.text(((target_w - sub2_w) // 2, target_h // 2 + 40), sub2, fill=(100, 200, 150), font=sub_font)
    
    return img

import numpy as np

def main():
    print("=" * 60)
    print("  HanumanAI Demo Video Creator")
    print("=" * 60)
    
    screenshots = get_sorted_screenshots()
    print(f"\nFound {len(screenshots)} screenshots for the demo")
    
    frames = []
    
    # === SECTION 1: 10-second Countdown ===
    print("\n[1/4] Creating 10-second countdown intro...")
    for i in range(10, 0, -1):
        frame = create_countdown_frame(i, TARGET_WIDTH, TARGET_HEIGHT)
        frames.append(np.array(frame))
    
    # GO! frame (show for 1 second)
    go_frame = create_launch_frame(TARGET_WIDTH, TARGET_HEIGHT)
    frames.append(np.array(go_frame))
    
    # === SECTION 2: Demo Screenshots ===
    print("[2/4] Processing demo screenshots...")
    
    # Section labels paired with screenshot indices
    sections = [
        (0, "Welcome & Onboarding", "First launch experience"),
        (1, "Agent Mode Switching", "Chat, Tasks, Code, Knowledge modes"),
        (5, "Chat Interface", "Sending messages & getting AI responses"),
        (8, "Settings Panel", "Model selection & temperature control"),
        (12, "Sidebar Controls", "Collapse, expand & navigation"),
        (20, "Theme Toggle", "Light and dark mode switching"),
    ]
    
    section_indices = {s[0]: (s[1], s[2]) for s in sections}
    
    for idx, screenshot_path in enumerate(screenshots):
        # Add section title frame if this is a section start
        if idx in section_indices:
            title, subtitle = section_indices[idx]
            section_frame = create_section_frame(title, subtitle, TARGET_WIDTH, TARGET_HEIGHT)
            # Show section title for 2 seconds (2 frames at 1fps equivalent = 4 frames at 2fps)
            for _ in range(4):
                frames.append(np.array(section_frame))
        
        try:
            img = Image.open(screenshot_path).convert('RGB')
            resized = resize_frame(img, TARGET_WIDTH, TARGET_HEIGHT)
            # Show each screenshot for 1.5 seconds (3 frames at 2fps)
            for _ in range(3):
                frames.append(np.array(resized))
            print(f"  [OK] Frame {idx + 1}/{len(screenshots)}: {os.path.basename(screenshot_path)}")
        except Exception as e:
            print(f"  [FAIL] Failed to load {screenshot_path}: {e}")
    
    # === SECTION 3: End Screen ===
    print("[3/4] Creating end screen...")
    end_frame = create_end_frame(TARGET_WIDTH, TARGET_HEIGHT)
    for _ in range(6):  # 3 seconds
        frames.append(np.array(end_frame))
    
    # === SECTION 4: Write MP4 ===
    print(f"[4/4] Writing MP4 video ({len(frames)} frames at {FPS} fps)...")
    print(f"  Output: {OUTPUT_PATH}")
    
    writer = imageio.get_writer(
        OUTPUT_PATH,
        fps=FPS,
        codec='libx264',
        quality=8,
        pixelformat='yuv420p',
        macro_block_size=8,
    )
    
    for frame in frames:
        writer.append_data(frame)
    
    writer.close()
    
    file_size = os.path.getsize(OUTPUT_PATH)
    duration = len(frames) / FPS
    
    print(f"\n{'=' * 60}")
    print(f"  [DONE] Video created successfully!")
    print(f"  File: {OUTPUT_PATH}")
    print(f"  Resolution: {TARGET_WIDTH}x{TARGET_HEIGHT}")
    print(f"  Duration: {duration:.1f} seconds")
    print(f"  Size: {file_size / (1024*1024):.1f} MB")
    print(f"  Total frames: {len(frames)}")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
