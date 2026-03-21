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


def _circle_avatar(avatar_bytes, size):
    av   = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((size, size), Image.LANCZOS)
    out  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L",    (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    out.paste(av, (0, 0))
    out.putalpha(mask)
    return out


def _bg(w, h, accent):
    img   = Image.new("RGBA", (w, h), (9, 11, 20, 255))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d     = ImageDraw.Draw(layer)
    r, g, b = accent
    for i in range(200, 0, -1):
        d.ellipse([-i*2, -i*2, i*3, i*3], fill=(r, g, b, int(i * 0.35)))
    for i in range(140, 0, -1):
        d.ellipse([w-i*2, h-i*2, w+i, h+i], fill=(r, g, b, int(i * 0.2)))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(70)))
    return img


def _progress(draw, x, y, w, h, pct, accent):
    r2 = h // 2
    draw.rounded_rectangle([x, y, x+w, y+h], radius=r2, fill=(16, 20, 42))
    fw = max(r2*2, int(w * pct / 100))
    r, g, b = accent
    rl, gl, bl = min(r+80, 255), min(g+80, 255), min(b+80, 255)
    draw.rounded_rectangle([x, y, x+fw, y+h], radius=r2, fill=(r, g, b))
    if fw > r2*2 + 6:
        draw.rounded_rectangle([x+4, y+3, x+fw-4, y+h//2+2],
                                radius=r2-3, fill=(rl, gl, bl))


def _stat_card(draw, x, y, w, h, label, value, accent):
    _rr(draw, [x, y, x+w, y+h], 16, fill=(12, 15, 31), outline=(30, 36, 75), width=2)
    r, g, b = accent
    draw.rounded_rectangle([x+4, y+4, x+w-4, y+10], radius=3, fill=(r, g, b))
    val_str = str(value)
    fs = 36 if len(val_str) <= 8 else 28
    draw.text((x + w//2, y + h//2 - 10), val_str,
              font=_f(_FONT_BOLD2, fs), fill=(240, 242, 255), anchor="mm")
    draw.text((x + w//2, y + h - 18), label,
              font=_f(_FONT_BOLD2, 18), fill=(110, 116, 168), anchor="mm")


def generate_profile_card(
    username, avatar_bytes, rank, level, total_xp,
    xp_progress, xp_needed, messages, reactions, vc_time,
    mentions, activity_type, peak_vc_hour, avg_daily_vc,
    longest_session, longest_session_date, vc_partners,
    favorite_game, favorite_game_time, response_ms,
):
    W, H = 1400, 720
    PAD  = 36

    accent, accent_l, rlabel = _rank_palette(rank)
    r, g, b = accent

    img  = _bg(W, H, accent)
    draw = ImageDraw.Draw(img)

    for i in range(5, 0, -1):
        draw.rounded_rectangle([i, i, W-i, H-i], radius=22-i,
                                outline=(r, g, b, 15 + i*8), width=1)

    # Avatar
    AV = 180
    av = _circle_avatar(avatar_bytes, AV)
    AX, AY = PAD, PAD
    img.alpha_composite(av, (AX, AY))

    # Rank badge
    badge_cx = AX + AV // 2
    badge_y  = AY + AV + 8
    bw, bh   = 100, 36
    _rr(draw, [badge_cx - bw//2, badge_y, badge_cx + bw//2, badge_y + bh],
        18, fill=(r, g, b, 230))
    draw.text((badge_cx, badge_y + bh//2), rlabel,
              font=_f(_FONT_BOLD2, 20), fill=(10, 12, 24), anchor="mm")

    # Username
    NX = AX + AV + 26
    NY = AY + 4
    dn = username[:22] + ("…" if len(username) > 22 else "")
    draw.text((NX, NY), dn, font=_f(_FONT_BOLD, 66), fill=(255, 255, 255))

    # Level pill
    pill_y    = NY + 76
    pill_text = f"LEVEL {level}"
    fp        = _f(_FONT_BOLD2, 22)
    pb        = draw.textbbox((0, 0), pill_text, font=fp)
    pw        = pb[2] - pb[0] + 36
    ph        = 42
    _rr(draw, [NX, pill_y, NX + pw, pill_y + ph], 21,
        fill=(r, g, b, 35), outline=(r, g, b, 180), width=2)
    draw.text((NX + pw//2, pill_y + ph//2), pill_text,
              font=fp, fill=accent_l, anchor="mm")
    draw.text((NX + pw + 18, pill_y + ph//2), f"{total_xp:,} XP",
              font=_f(_FONT_SB2, 24), fill=(155, 160, 205), anchor="lm")

    # Progress label
    bar_lbl_y = pill_y + ph + 20
    draw.text((NX, bar_lbl_y), f"Progress to Level {level + 1}",
              font=_f(_FONT_REG2, 20), fill=(80, 86, 128))

    # Progress bar
    bar_y = bar_lbl_y + 28
    bar_w = W - NX - PAD
    bar_h = 22
    pct   = int((xp_progress / xp_needed) * 100) if xp_needed > 0 else 100
    _progress(draw, NX, bar_y, bar_w, bar_h, pct, accent)

    # XP counts
    xp_y = bar_y + bar_h + 10
    draw.text((NX, xp_y), f"{xp_progress:,} / {xp_needed:,} XP",
              font=_f(_FONT_REG2, 20), fill=(100, 106, 155))
    draw.text((NX + bar_w, xp_y), f"{pct}%",
              font=_f(_FONT_BOLD2, 20), fill=accent_l, anchor="ra")

    # Divider
    div_y = max(AY + AV + bh + 30, xp_y + 34)
    draw.line([(PAD, div_y), (W - PAD, div_y)], fill=(30, 36, 70, 200), width=2)

    # 6 stat cards
    act = (activity_type
           .replace("🌅","").replace("☀️","").replace("🌆","")
           .replace("🦉","").replace("❓","").strip())
    act = act if len(act) <= 12 else act.split()[0]

    stats = [
        ("MESSAGES",  f"{messages:,}"),
        ("REACTIONS", f"{reactions:,}"),
        ("VC TIME",   vc_time),
        ("MENTIONED", f"{mentions:,}"),
        ("ACTIVITY",  act),
        ("PEAK VC",   peak_vc_hour or "—"),
    ]

    st_top = div_y + 14
    st_h   = 100
    st_gap = 8
    st_w   = (W - PAD*2 - st_gap*5) // 6

    for i, (lbl, val) in enumerate(stats):
        _stat_card(draw, PAD + i*(st_w + st_gap), st_top, st_w, st_h, lbl, val, accent)

    # Bottom panels
    bot_y  = st_top + st_h + 14
    bot_h  = H - bot_y - PAD
    left_w = 520

    # VC Partners
    _rr(draw, [PAD, bot_y, PAD + left_w, bot_y + bot_h],
        14, fill=(11, 14, 28), outline=(30, 36, 75), width=2)
    draw.text((PAD + left_w//2, bot_y + 20), "TOP VC PARTNERS",
              font=_f(_FONT_BOLD2, 20), fill=accent_l, anchor="mm")
    draw.line([(PAD + 16, bot_y + 34), (PAD + left_w - 16, bot_y + 34)],
              fill=(30, 36, 70), width=1)

    if vc_partners:
        mc_list = [accent, (170, 180, 205), (180, 115, 62)]
        cw = left_w // min(len(vc_partners), 3)
        for i, (pn, pt) in enumerate(vc_partners[:3]):
            cx = PAD + i*cw + cw//2
            mc = mc_list[i]
            draw.text((cx, bot_y + 54),  ["1ST", "2ND", "3RD"][i],
                      font=_f(_FONT_BOLD2, 18), fill=mc, anchor="mm")
            pn_d = pn[:14] + ("…" if len(pn) > 14 else "")
            draw.text((cx, bot_y + 82),  pn_d,
                      font=_f(_FONT_SB2, 24), fill=(222, 228, 255), anchor="mm")
            draw.text((cx, bot_y + 110), pt,
                      font=_f(_FONT_LIGHT2, 20), fill=(92, 97, 138), anchor="mm")
    else:
        draw.text((PAD + left_w//2, bot_y + bot_h//2), "No VC data yet",
                  font=_f(_FONT_LIGHT2, 22), fill=(58, 63, 95), anchor="mm")

    # Right column
    rx   = PAD + left_w + 14
    rw   = W - rx - PAD
    tp_h = (bot_h - 12) // 2
    cw2  = (rw - 10) // 2

    for i, (lbl, val, sub) in enumerate([
        ("AVG DAILY VC",    avg_daily_vc,     ""),
        ("LONGEST SESSION", longest_session,  longest_session_date or ""),
    ]):
        tx = rx + i*(cw2 + 10)
        _rr(draw, [tx, bot_y, tx + cw2, bot_y + tp_h],
            14, fill=(11, 14, 28), outline=(30, 36, 75), width=2)
        draw.text((tx + cw2//2, bot_y + 18), lbl,
                  font=_f(_FONT_BOLD2, 16), fill=(88, 94, 136), anchor="mm")
        draw.text((tx + cw2//2, bot_y + tp_h//2 + 4), val,
                  font=_f(_FONT_BOLD2, 26), fill=(232, 236, 255), anchor="mm")
        if sub:
            draw.text((tx + cw2//2, bot_y + tp_h - 16), sub,
                      font=_f(_FONT_REG2, 17), fill=(72, 77, 115), anchor="mm")

    # Favourite game
    gy = bot_y + tp_h + 12
    gh = bot_h - tp_h - 12
    _rr(draw, [rx, gy, rx + rw, gy + gh],
        14, fill=(11, 14, 28), outline=(30, 36, 75), width=2)
    if favorite_game:
        draw.text((rx + rw//2, gy + 18), "FAVORITE GAME",
                  font=_f(_FONT_BOLD2, 16), fill=(88, 94, 136), anchor="mm")
        fg = favorite_game[:26] + ("…" if len(favorite_game) > 26 else "")
        draw.text((rx + rw//2, gy + gh//2 + 2), fg,
                  font=_f(_FONT_BOLD, 24), fill=(238, 241, 255), anchor="mm")
        draw.text((rx + rw//2, gy + gh - 14), favorite_game_time,
                  font=_f(_FONT_LIGHT2, 18), fill=(92, 97, 138), anchor="mm")
    else:
        draw.text((rx + rw//2, gy + gh//2), "No games tracked",
                  font=_f(_FONT_LIGHT2, 20), fill=(58, 63, 95), anchor="mm")

    # Footer
    draw.text((W - PAD, H - 12), f"⚡ {response_ms}",
              font=_f(_FONT_LIGHT2, 15), fill=(48, 53, 82), anchor="ra")

    # Export
    out = Image.new("RGB", (W, H), (9, 11, 20))
    out.paste(img, mask=img.split()[3])
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()