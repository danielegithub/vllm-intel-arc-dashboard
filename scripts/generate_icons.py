#!/usr/bin/env python3
import os
from PIL import Image, ImageDraw

def create_dashboard_icon(state="active", size=(128, 128)):
    # Colors
    bg_color = (20, 24, 35, 255)
    border_color = (0, 104, 230, 255) # Intel Arc Blue
    inner_chip_color = (30, 36, 52, 255)
    
    if state == "active":
        badge_color = (16, 185, 129, 255) # Emerald green
        glow_color = (16, 185, 129, 110)
    elif state == "starting":
        badge_color = (245, 158, 11, 255) # Amber yellow
        glow_color = (245, 158, 11, 110)
    else: # inactive
        badge_color = (239, 68, 68, 255) # Red
        glow_color = (239, 68, 68, 110)

    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    w, h = size

    # Outer rounded rectangle (GPU / Chip shape)
    margin = int(w * 0.08)
    corner_radius = int(w * 0.18)
    draw.rounded_rectangle(
        [margin, margin, w - margin, h - margin],
        radius=corner_radius,
        fill=bg_color,
        outline=border_color,
        width=max(2, int(w * 0.035))
    )

    # Internal microchip core
    chip_margin = int(w * 0.22)
    draw.rounded_rectangle(
        [chip_margin, chip_margin, w - chip_margin, h - chip_margin],
        radius=int(w * 0.08),
        fill=inner_chip_color,
        outline=(0, 150, 255, 180),
        width=max(1, int(w * 0.02))
    )

    # Stylized "V" inside the chip for vLLM
    v_top = int(h * 0.32)
    v_bottom = int(h * 0.58)
    v_left = int(w * 0.32)
    v_mid = int(w * 0.5)
    v_right = int(w * 0.68)
    line_w = max(3, int(w * 0.065))
    draw.line([(v_left, v_top), (v_mid, v_bottom)], fill=(255, 255, 255, 240), width=line_w)
    draw.line([(v_mid, v_bottom), (v_right, v_top)], fill=(0, 200, 255, 255), width=line_w)

    # Status LED in bottom-right corner
    led_radius = int(w * 0.14)
    led_x = int(w * 0.78)
    led_y = int(h * 0.78)
    
    # Glow
    glow_r = int(led_radius * 1.5)
    draw.ellipse(
        [led_x - glow_r, led_y - glow_r, led_x + glow_r, led_y + glow_r],
        fill=glow_color
    )
    # LED body
    draw.ellipse(
        [led_x - led_radius, led_y - led_radius, led_x + led_radius, led_y + led_radius],
        fill=badge_color,
        outline=(255, 255, 255, 220),
        width=max(1, int(w * 0.02))
    )

    return img

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assets_dir = os.path.join(base_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    # Generate icons
    icon_active = create_dashboard_icon("active", (128, 128))
    icon_active.save(os.path.join(assets_dir, "icon-active.png"))

    icon_inactive = create_dashboard_icon("inactive", (128, 128))
    icon_inactive.save(os.path.join(assets_dir, "icon-inactive.png"))

    icon_starting = create_dashboard_icon("starting", (128, 128))
    icon_starting.save(os.path.join(assets_dir, "icon-starting.png"))

    icon_logo = create_dashboard_icon("active", (256, 256))
    icon_logo.save(os.path.join(assets_dir, "vllm-logo.png"))

    print(f"Icons generated successfully in {assets_dir}")

if __name__ == "__main__":
    main()
