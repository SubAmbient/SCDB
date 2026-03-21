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
    """Simple circular crop — no ring, no glow."""
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
    for i in range(130, 0, -1):
        d.ellipse([-i*2, -i*2, i*3, i*3], fill=(r, g, b, int(i * 0.4)))
    for i in range(90, 0, -1):
        d.ellipse([w-i*2, h-i*2, w+i, h+i], fill=(r, g, b, int(i * 0.25)))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(55)))
    return img


def _progress(draw, x, y, w, h, pct, accent):
    r2 = h // 2
    draw.rounded_rectangle([x, y, x+w, y+h], radius=r2, fill=(16, 20, 42))
    fw = max(r2*2, int(w * pct / 100))
    r, g, b = accent
    rl, gl, bl = min(r+80, 255), min(g+80, 255), min(b+80, 255)
    draw.rounded_rectangle([x, y, x+fw, y+h], radius=r2, fill=(r, g, b))
    if fw > r2*2 + 4:
        draw.rounded_rectangle([x+3, y+2, x+fw-3, y+h//2+1],
                                radius=r2-2, fill=(rl, gl, bl))


def _stat(draw, x, y, w, h, label, value, accent):
    _rr(draw, [x, y, x+w, y+h], 12, fill=(12, 15, 31), outline=(24, 29, 60), width=1)
    r, g, b = accent
    draw.rounded_rectangle([x+3, y+3, x+w-3, y+7], radius=3, fill=(r, g, b))
    # Value — shrink font if the text is long
    fs = 26 if len(str(value)) <= 9 else 20
    draw.text((x+w//2, y+h//2 - 8), str(value),
              font=_f(_FONT_BOLD2, fs), fill=(240, 242, 255), anchor="mm")
    draw.text((x+w//2, y+h - 14), label,
              font=_f(_FONT_BOLD2, 13), fill=(95, 100, 148), anchor="mm")


def generate_profile_card(
    username, avatar_bytes, rank, level, total_xp,
    xp_progress, xp_needed, messages, reactions, vc_time,
    mentions, activity_type, peak_vc_hour, avg_daily_vc,
    longest_session, longest_session_date, vc_partners,
    favorite_game, favorite_game_time, response_ms,
):
    # ── Canvas ───────────────────────────────────────────────────────────────
    W, H = 1020, 580
    PAD  = 28          # outer padding
    accent, accent_l, rlabel = _rank_palette(rank)
    r, g, b = accent

    img  = _bg(W, H, accent)
    draw = ImageDraw.Draw(img)

    # Subtle border glow
    for i in range(5, 0, -1):
        draw.rounded_rectangle([i, i, W-i, H-i], radius=20-i,
                                outline=(r, g, b, 18 + i*6), width=1)

    # ── Avatar (no ring) ────────────────────────────────────────────────────
    AV_SIZE = 148
    av = _circle_avatar(avatar_bytes, AV_SIZE)
    AX, AY = PAD, PAD
    img.alpha_composite(av, (AX, AY))

    # Rank badge centred under the avatar
    badge_cx = AX + AV_SIZE // 2
    badge_y  = AY + AV_SIZE + 6
    fb = _f(_FONT_BOLD2, 16)
    bw, bh = 76, 28
    _rr(draw, [badge_cx - bw//2, badge_y, badge_cx + bw//2, badge_y + bh],
        14, fill=(r, g, b, 220))
    draw.text((badge_cx, badge_y + bh//2), rlabel,
              font=fb, fill=(10, 12, 24), anchor="mm")

    # ── Header text block ───────────────────────────────────────────────────
    NX = AX + AV_SIZE + 20   # left edge of text column
    NY = AY + 6

    # Username  (52 px)
    dn = username[:20] + ("…" if len(username) > 20 else "")
    draw.text((NX, NY), dn, font=_f(_FONT_BOLD, 52), fill=(255, 255, 255))

    # Level pill + XP total  — placed 62 px below username baseline
    pill_y = NY + 62
    pill_text = f"LEVEL {level}"
    fp  = _f(_FONT_BOLD2, 17)
    pb  = draw.textbbox((0, 0), pill_text, font=fp)
    pw  = pb[2] - pb[0] + 28
    ph  = 32
    _rr(draw, [NX, pill_y, NX + pw, pill_y + ph], 16,
        fill=(r, g, b, 35), outline=(r, g, b, 160), width=1)
    draw.text((NX + pw//2, pill_y + ph//2), pill_text,
              font=fp, fill=accent_l, anchor="mm")
    draw.text((NX + pw + 14, pill_y + ph//2), f"{total_xp:,} XP",
              font=_f(_FONT_SB2, 18), fill=(155, 160, 205), anchor="lm")

    # Progress label
    bar_label_y = pill_y + ph + 18
    draw.text((NX, bar_label_y), f"Progress to Level {level + 1}",
              font=_f(_FONT_REG2, 15), fill=(72, 77, 114))

    # Progress bar
    bar_y  = bar_label_y + 22
    bar_w  = W - NX - PAD
    bar_h  = 18
    pct    = int((xp_progress / xp_needed) * 100) if xp_needed > 0 else 100
    _progress(draw, NX, bar_y, bar_w, bar_h, pct, accent)

    # XP numbers below the bar
    xp_label_y = bar_y + bar_h + 8
    draw.text((NX, xp_label_y), f"{xp_progress:,} / {xp_needed:,} XP",
              font=_f(_FONT_REG2, 15), fill=(95, 100, 145))
    draw.text((NX + bar_w, xp_label_y), f"{pct}%",
              font=_f(_FONT_BOLD2, 15), fill=accent_l, anchor="ra")

    # ── Horizontal divider ──────────────────────────────────────────────────
    # Place divider below whichever section is taller
    # (avatar block goes to: AY + AV_SIZE + 6 + 28 = AY + 182)
    # (text block goes to:   xp_label_y + ~20)
    div_y = max(AY + AV_SIZE + 6 + bh + 14,
                xp_label_y + 22)
    draw.line([(PAD, div_y), (W - PAD, div_y)], fill=(26, 31, 64, 180), width=1)

    # ── 6 Stat cards ────────────────────────────────────────────────────────
    act = (activity_type
           .replace("🌅","").replace("☀️","").replace("🌆","")
           .replace("🦉","").replace("❓","").strip())
    act = act if len(act) <= 11 else act.split()[0]

    stats = [
        ("MESSAGES",  f"{messages:,}"),
        ("REACTIONS", f"{reactions:,}"),
        ("VC TIME",   vc_time),
        ("MENTIONED", f"{mentions:,}"),
        ("ACTIVITY",  act),
        ("PEAK VC",   peak_vc_hour or "—"),
    ]

    stat_top = div_y + 12
    stat_h   = 84
    stat_gap = 7
    stat_w   = (W - PAD*2 - stat_gap*5) // 6

    for i, (lbl, val) in enumerate(stats):
        _stat(draw, PAD + i*(stat_w + stat_gap), stat_top, stat_w, stat_h, lbl, val, accent)

    # ── Bottom section ───────────────────────────────────────────────────────
    bot_y  = stat_top + stat_h + 12
    bot_h  = H - bot_y - PAD          # remaining height
    left_w = 450                       # VC partners panel width

    # ── VC Partners (left) ──────────────────────────────────────────────────
    _rr(draw, [PAD, bot_y, PAD + left_w, bot_y + bot_h],
        12, fill=(11, 14, 28), outline=(24, 29, 60), width=1)
    draw.text((PAD + left_w//2, bot_y + 16), "TOP VC PARTNERS",
              font=_f(_FONT_BOLD2, 15), fill=accent_l, anchor="mm")
    draw.line([(PAD + 14, bot_y + 28), (PAD + left_w - 14, bot_y + 28)],
              fill=(26, 31, 64), width=1)

    if vc_partners:
        mc_list = [accent, (170, 180, 205), (180, 115, 62)]
        cw = left_w // min(len(vc_partners), 3)
        for i, (pn, pt) in enumerate(vc_partners[:3]):
            cx = PAD + i*cw + cw//2
            mc = mc_list[i]
            draw.text((cx, bot_y + 44), ["1ST", "2ND", "3RD"][i],
                      font=_f(_FONT_BOLD2, 14), fill=mc, anchor="mm")
            pn_disp = pn[:16] + ("…" if len(pn) > 16 else "")
            draw.text((cx, bot_y + 66), pn_disp,
                      font=_f(_FONT_SB2, 18), fill=(222, 228, 255), anchor="mm")
            draw.text((cx, bot_y + 88), pt,
                      font=_f(_FONT_LIGHT2, 15), fill=(92, 97, 138), anchor="mm")
    else:
        draw.text((PAD + left_w//2, bot_y + bot_h//2 + 5), "No VC data yet",
                  font=_f(_FONT_LIGHT2, 16), fill=(58, 63, 95), anchor="mm")

    # ── Right column ─────────────────────────────────────────────────────────
    rx  = PAD + left_w + 12
    rw  = W - rx - PAD
    top_h   = (bot_h - 10) // 2
    cell_w  = (rw - 8) // 2

    for i, (lbl, val, sub) in enumerate([
        ("AVG DAILY VC",    avg_daily_vc,      ""),
        ("LONGEST SESSION", longest_session,   longest_session_date or ""),
    ]):
        tx = rx + i*(cell_w + 8)
        _rr(draw, [tx, bot_y, tx + cell_w, bot_y + top_h],
            12, fill=(11, 14, 28), outline=(24, 29, 60), width=1)
        draw.text((tx + cell_w//2, bot_y + 14), lbl,
                  font=_f(_FONT_BOLD2, 12), fill=(88, 94, 136), anchor="mm")
        draw.text((tx + cell_w//2, bot_y + top_h//2 + 4), val,
                  font=_f(_FONT_BOLD2, 20), fill=(232, 236, 255), anchor="mm")
        if sub:
            draw.text((tx + cell_w//2, bot_y + top_h - 12), sub,
                      font=_f(_FONT_REG2, 13), fill=(72, 77, 115), anchor="mm")

    # ── Favourite game ───────────────────────────────────────────────────────
    gy = bot_y + top_h + 10
    gh = bot_h - top_h - 10
    _rr(draw, [rx, gy, rx + rw, gy + gh],
        12, fill=(11, 14, 28), outline=(24, 29, 60), width=1)
    if favorite_game:
        draw.text((rx + rw//2, gy + 14), "FAVORITE GAME",
                  font=_f(_FONT_BOLD2, 12), fill=(88, 94, 136), anchor="mm")
        fg = favorite_game[:24] + ("…" if len(favorite_game) > 24 else "")
        draw.text((rx + rw//2, gy + gh//2 + 2), fg,
                  font=_f(_FONT_BOLD, 18), fill=(238, 241, 255), anchor="mm")
        draw.text((rx + rw//2, gy + gh - 12), favorite_game_time,
                  font=_f(_FONT_LIGHT2, 14), fill=(92, 97, 138), anchor="mm")
    else:
        draw.text((rx + rw//2, gy + gh//2), "No games tracked",
                  font=_f(_FONT_LIGHT2, 15), fill=(58, 63, 95), anchor="mm")

    # ── Footer ───────────────────────────────────────────────────────────────
    draw.text((W - PAD, H - 10), f"⚡ {response_ms}",
              font=_f(_FONT_LIGHT2, 12), fill=(48, 53, 82), anchor="ra")

    # ── Export ───────────────────────────────────────────────────────────────
    out = Image.new("RGB", (W, H), (9, 11, 20))
    out.paste(img, mask=img.split()[3])
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()