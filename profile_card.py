"""
profile_card.py — Generates a beautiful profile card image for the Shame Club Bot.
Drop this file next to bot.py and add the import at the top of bot.py.

Requirements:
    pip install Pillow aiohttp

Font paths (Linux):
    sudo apt-get install fonts-ubuntu fonts-open-sans
"""

import io
from PIL import Image, ImageDraw, ImageFont, ImageFilter


_FONT_BOLD   = "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf"
_FONT_MED    = "/usr/share/fonts/truetype/ubuntu/Ubuntu-M.ttf"
_FONT_LIGHT  = "/usr/share/fonts/truetype/ubuntu/Ubuntu-L.ttf"
_FONT_BOLD2  = "/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf"
_FONT_SB2    = "/usr/share/fonts/truetype/open-sans/OpenSans-Semibold.ttf"
_FONT_REG2   = "/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf"
_FONT_LIGHT2 = "/usr/share/fonts/truetype/open-sans/OpenSans-Light.ttf"

def _f(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        try:
            return ImageFont.truetype(_FONT_BOLD2, size)
        except Exception:
            return ImageFont.load_default()


def _rank_palette(rank: int):
    if   rank == 1: return (255, 200,  40), (255, 230, 120), "1ST"
    elif rank == 2: return (140, 170, 255), (200, 215, 255), "2ND"
    elif rank == 3: return (210, 130,  60), (240, 170,  90), "3RD"
    else:           return ( 88, 101, 242), (130, 145, 255), f"#{rank}"


def _rr(draw, xy, rad, fill=None, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=rad, fill=fill, outline=outline, width=width)


def _circle_avatar(avatar_bytes, size, ring_rgb, ring_w=5):
    av    = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((size, size), Image.LANCZOS)
    pad   = ring_w + 5
    total = size + pad * 2
    out   = Image.new("RGBA", (total, total), (0,0,0,0))

    # Glow halo
    glow = Image.new("RGBA", (total, total), (0,0,0,0))
    gd   = ImageDraw.Draw(glow)
    r, g, b = ring_rgb
    for i in range(16, 0, -1):
        gd.ellipse([pad-i, pad-i, total-pad+i, total-pad+i],
                   outline=(r, g, b, int(i*5)), width=2)
    out.alpha_composite(glow.filter(ImageFilter.GaussianBlur(3)))

    # Solid ring
    rl = Image.new("RGBA", (total, total), (0,0,0,0))
    rd = ImageDraw.Draw(rl)
    rd.ellipse([pad-ring_w, pad-ring_w, total-pad+ring_w, total-pad+ring_w], fill=(r,g,b,255))
    out.alpha_composite(rl)

    # Avatar masked to circle
    al   = Image.new("RGBA", (total, total), (0,0,0,0))
    mask = Image.new("L", (total, total), 0)
    ImageDraw.Draw(mask).ellipse([pad, pad, total-pad, total-pad], fill=255)
    al.paste(av, (pad, pad))
    al.putalpha(mask)
    out.alpha_composite(al)
    return out


def _bg(w, h, accent):
    img   = Image.new("RGBA", (w, h), (9, 11, 20, 255))
    layer = Image.new("RGBA", (w, h), (0,0,0,0))
    d     = ImageDraw.Draw(layer)
    r, g, b = accent
    for i in range(110, 0, -1):
        d.ellipse([-i*2, -i*2, i*3, i*3], fill=(r, g, b, int(i*0.4)))
    for i in range(80, 0, -1):
        d.ellipse([w-i*2, h-i*2, w+i, h+i], fill=(r, g, b, int(i*0.25)))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(50)))
    return img


def _progress(draw, x, y, w, h, pct, accent):
    r2 = h // 2
    draw.rounded_rectangle([x, y, x+w, y+h], radius=r2, fill=(16, 20, 42))
    fw = max(r2*2, int(w * pct / 100))
    r, g, b = accent
    rl, gl, bl = min(r+80,255), min(g+80,255), min(b+80,255)
    draw.rounded_rectangle([x, y, x+fw, y+h], radius=r2, fill=(r,g,b))
    if fw > r2*2 + 4:
        draw.rounded_rectangle([x+3, y+2, x+fw-3, y+h//2+1],
                                radius=r2-2, fill=(rl, gl, bl))


def _stat(draw, x, y, w, h, label, value, accent):
    _rr(draw, [x,y,x+w,y+h], 10, fill=(12,15,31), outline=(24,29,60), width=1)
    r, g, b = accent
    draw.rounded_rectangle([x+2, y+2, x+w-2, y+5], radius=2, fill=(r,g,b))
    fs = 23 if len(str(value)) <= 9 else 17
    draw.text((x+w//2, y+h//2-4), str(value), font=_f(_FONT_BOLD2, fs),
              fill=(240,242,255), anchor="mm")
    draw.text((x+w//2, y+h-10), label, font=_f(_FONT_REG2, 11),
              fill=(95,100,148), anchor="mm")


def generate_profile_card(
    username, avatar_bytes, rank, level, total_xp,
    xp_progress, xp_needed, messages, reactions, vc_time,
    mentions, activity_type, peak_vc_hour, avg_daily_vc,
    longest_session, longest_session_date, vc_partners,
    favorite_game, favorite_game_time, response_ms,
):
    W, H = 960, 510
    accent, accent_l, rlabel = _rank_palette(rank)
    r, g, b = accent

    img  = _bg(W, H, accent)
    draw = ImageDraw.Draw(img)

    # Border glow
    for i in range(5, 0, -1):
        draw.rounded_rectangle([i,i,W-i,H-i], radius=18-i,
                               outline=(r,g,b,20+i*7), width=1)

    # Divider
    draw.line([(24,236),(W-24,236)], fill=(26,31,64,160), width=1)

    # ── Avatar ──────────────────────────────────────────────────────────────
    AV = 130
    av  = _circle_avatar(avatar_bytes, AV, accent, ring_w=5)
    ax, ay = 20, 22
    img.alpha_composite(av, (ax, ay))

    # Rank badge
    bx = ax + av.width // 2
    by = ay + av.height + 4
    fb = _f(_FONT_BOLD2, 14)
    bw, bh = 68, 24
    _rr(draw, [bx-bw//2, by, bx+bw//2, by+bh], 12, fill=(r,g,b,220))
    draw.text((bx, by+bh//2), rlabel, font=fb, fill=(10,12,24), anchor="mm")

    # ── Name ────────────────────────────────────────────────────────────────
    nx = ax + av.width + 14
    ny = 28
    dn = username[:18] + ("…" if len(username) > 18 else "")
    draw.text((nx, ny), dn, font=_f(_FONT_BOLD, 44), fill=(255,255,255))

    # Level pill + XP
    py = ny + 53
    pill = f"LEVEL {level}"
    fp   = _f(_FONT_BOLD2, 14)
    pb   = draw.textbbox((0,0), pill, font=fp)
    pw   = pb[2]-pb[0] + 24
    _rr(draw, [nx, py, nx+pw, py+26], 13,
        fill=(r,g,b,35), outline=(r,g,b,150), width=1)
    draw.text((nx+pw//2, py+13), pill, font=fp, fill=accent_l, anchor="mm")
    draw.text((nx+pw+12, py+13), f"{total_xp:,} XP",
              font=_f(_FONT_SB2, 15), fill=(155,160,205), anchor="lm")

    # Progress bar
    bpy = py + 37
    bpw = W - nx - 26
    bph = 14
    pct = int((xp_progress / xp_needed) * 100) if xp_needed > 0 else 100
    _progress(draw, nx, bpy, bpw, bph, pct, accent)
    draw.text((nx, bpy-5), f"Progress to Level {level+1}",
              font=_f(_FONT_LIGHT2, 12), fill=(72,77,114), anchor="lb")
    draw.text((nx, bpy+bph+6), f"{xp_progress:,} / {xp_needed:,} XP",
              font=_f(_FONT_REG2, 13), fill=(95,100,145))
    draw.text((nx+bpw, bpy+bph+6), f"{pct}%",
              font=_f(_FONT_BOLD2, 13), fill=accent_l, anchor="ra")

    # ── 6 Stat cards ────────────────────────────────────────────────────────
    act = (activity_type.replace("🌅","").replace("☀️","").replace("🌆","")
           .replace("🦉","").replace("❓","").strip())
    act = act if len(act) <= 10 else act.split()[0]

    stats = [
        ("MESSAGES",  f"{messages:,}"),
        ("REACTIONS", f"{reactions:,}"),
        ("VC TIME",   vc_time),
        ("MENTIONED", f"{mentions:,}"),
        ("ACTIVITY",  act),
        ("PEAK VC",   peak_vc_hour or "—"),
    ]
    st = 248
    sp = 6
    sw = (W - 56 - sp*5) // 6
    sh = 72
    for i, (lbl, val) in enumerate(stats):
        _stat(draw, 28 + i*(sw+sp), st, sw, sh, lbl, val, accent)

    # ── Bottom ───────────────────────────────────────────────────────────────
    boty = st + sh + 10
    both = H - boty - 12
    lw   = 436

    # VC Partners
    _rr(draw, [28, boty, 28+lw, boty+both], 10,
        fill=(11,14,28), outline=(24,29,60), width=1)
    draw.text((28+lw//2, boty+13), "TOP VC PARTNERS",
              font=_f(_FONT_BOLD2, 13), fill=accent_l, anchor="mm")
    draw.line([(44,boty+24),(28+lw-16,boty+24)], fill=(26,31,64), width=1)

    if vc_partners:
        mc_list = [accent, (170,180,205), (180,115,62)]
        cw = lw // min(len(vc_partners), 3)
        for i, (pn, pt) in enumerate(vc_partners[:3]):
            cx = 28 + i*cw + cw//2
            mc = mc_list[i]
            draw.text((cx, boty+38), ["1ST","2ND","3RD"][i],
                      font=_f(_FONT_BOLD2, 12), fill=mc, anchor="mm")
            draw.text((cx, boty+57), pn[:14],
                      font=_f(_FONT_SB2, 16), fill=(222,228,255), anchor="mm")
            draw.text((cx, boty+74), pt,
                      font=_f(_FONT_LIGHT2, 13), fill=(92,97,138), anchor="mm")
    else:
        draw.text((28+lw//2, boty+both//2+5), "No VC data yet",
                  font=_f(_FONT_LIGHT2, 14), fill=(58,63,95), anchor="mm")

    # Right column
    rx  = 28 + lw + 10
    rw  = W - rx - 28
    tph = both//2 - 5
    tcw = (rw - 6) // 2

    for i, (lbl, val, sub) in enumerate([
        ("AVG DAILY VC",    avg_daily_vc, ""),
        ("LONGEST SESSION", longest_session, longest_session_date or ""),
    ]):
        tx = rx + i*(tcw+6)
        _rr(draw, [tx, boty, tx+tcw, boty+tph], 10,
            fill=(11,14,28), outline=(24,29,60), width=1)
        draw.text((tx+tcw//2, boty+11), lbl,
                  font=_f(_FONT_BOLD2, 10), fill=(88,94,136), anchor="mm")
        draw.text((tx+tcw//2, boty+tph//2+4), val,
                  font=_f(_FONT_BOLD2, 17), fill=(232,236,255), anchor="mm")
        if sub:
            draw.text((tx+tcw//2, boty+tph-9), sub,
                      font=_f(_FONT_REG2, 11), fill=(72,77,115), anchor="mm")

    # Fav game
    gy = boty + tph + 8
    gh = both - tph - 8
    _rr(draw, [rx, gy, rx+rw, gy+gh], 10, fill=(11,14,28), outline=(24,29,60), width=1)
    if favorite_game:
        draw.text((rx+rw//2, gy+11), "FAVORITE GAME",
                  font=_f(_FONT_BOLD2, 10), fill=(88,94,136), anchor="mm")
        fg = favorite_game[:22]+("…" if len(favorite_game)>22 else "")
        draw.text((rx+rw//2, gy+gh//2+1), fg,
                  font=_f(_FONT_BOLD, 15), fill=(238,241,255), anchor="mm")
        draw.text((rx+rw//2, gy+gh-9), favorite_game_time,
                  font=_f(_FONT_LIGHT2, 12), fill=(92,97,138), anchor="mm")
    else:
        draw.text((rx+rw//2, gy+gh//2), "No games tracked",
                  font=_f(_FONT_LIGHT2, 13), fill=(58,63,95), anchor="mm")

    # Footer
    draw.text((W-12, H-9), f"⚡ {response_ms}",
              font=_f(_FONT_LIGHT2, 11), fill=(48,53,82), anchor="ra")

    # Export
    out = Image.new("RGB", (W, H), (9, 11, 20))
    out.paste(img, mask=img.split()[3])
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()
