"""
profile_card.py — Generates a profile card for the Shame Club Bot.
Designed at 550px wide so Discord renders it near native size (no scaling down).
"""

import io
from PIL import Image, ImageDraw, ImageFont, ImageFilter

_FONT_BOLD   = "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf"
_FONT_BOLD2  = "/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf"
_FONT_SB2    = "/usr/share/fonts/truetype/open-sans/OpenSans-Semibold.ttf"
_FONT_REG2   = "/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf"
_FONT_LIGHT2 = "/usr/share/fonts/truetype/open-sans/OpenSans-Light.ttf"


def _f(path, size):
    for p in (path, _FONT_BOLD2):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _rank_palette(rank):
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
    for i in range(120, 0, -1):
        d.ellipse([-i, -i, i*2, i*2], fill=(r, g, b, int(i * 0.5)))
    for i in range(80, 0, -1):
        d.ellipse([w-i, h-i, w+i//2, h+i//2], fill=(r, g, b, int(i * 0.3)))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(40)))
    return img


def _progress_bar(draw, x, y, w, h, pct, accent):
    r2 = h // 2
    draw.rounded_rectangle([x, y, x+w, y+h], radius=r2, fill=(20, 24, 50))
    fw = max(r2*2, int(w * pct / 100))
    r, g, b = accent
    draw.rounded_rectangle([x, y, x+fw, y+h], radius=r2, fill=(r, g, b))
    hl = (min(r+90,255), min(g+90,255), min(b+90,255))
    if fw > r2*2 + 4:
        draw.rounded_rectangle([x+3, y+2, x+fw-3, y+h//2+1], radius=r2-2, fill=hl)


def generate_profile_card(
    username, avatar_bytes, rank, level, total_xp,
    xp_progress, xp_needed, messages, reactions, vc_time,
    mentions, activity_type, peak_vc_hour, avg_daily_vc,
    longest_session, longest_session_date, vc_partners,
    favorite_game, favorite_game_time, response_ms,
):
    # ── Canvas: 550 wide so Discord doesn't scale it down ───────────────────
    W   = 550
    PAD = 20
    accent, accent_l, rlabel = _rank_palette(rank)
    r, g, b = accent

    # ── Layout constants ────────────────────────────────────────────────────
    AV       = 90          # avatar diameter
    ROW1_H   = AV + 14     # header row height
    BAR_SEC  = 58          # xp bar section height
    STAT_H   = 76          # each stat card height
    PART_H   = 130         # VC partners panel
    BOTTOM_H = 90          # avg/longest/game row

    H = PAD + ROW1_H + BAR_SEC + STAT_H + STAT_H + 10 + PART_H + 10 + BOTTOM_H + PAD

    img  = _bg(W, H, accent)
    draw = ImageDraw.Draw(img)

    # Border
    for i in range(4, 0, -1):
        draw.rounded_rectangle([i,i,W-i,H-i], radius=14-i,
                                outline=(r,g,b, 20+i*10), width=1)

    # ── Avatar ───────────────────────────────────────────────────────────────
    av = _circle_avatar(avatar_bytes, AV)
    AX, AY = PAD, PAD
    img.alpha_composite(av, (AX, AY))

    # Rank badge under avatar
    bcx  = AX + AV//2
    by   = AY + AV + 4
    bw,bh = 68, 24
    _rr(draw, [bcx-bw//2, by, bcx+bw//2, by+bh], 12, fill=(r,g,b,220))
    draw.text((bcx, by+bh//2), rlabel, font=_f(_FONT_BOLD2, 15), fill=(10,12,24), anchor="mm")

    # ── Name + level ─────────────────────────────────────────────────────────
    NX = AX + AV + 16
    NY = AY

    dn = username[:18] + ("…" if len(username) > 18 else "")
    draw.text((NX, NY), dn, font=_f(_FONT_BOLD, 38), fill=(255, 255, 255))

    # Level pill
    py   = NY + 46
    pt   = f"LEVEL {level}"
    fp   = _f(_FONT_BOLD2, 17)
    pb   = draw.textbbox((0,0), pt, font=fp)
    pw   = pb[2]-pb[0]+24;  ph = 30
    _rr(draw, [NX, py, NX+pw, py+ph], 15, fill=(r,g,b,40), outline=(r,g,b,180), width=2)
    draw.text((NX+pw//2, py+ph//2), pt, font=fp, fill=accent_l, anchor="mm")
    draw.text((NX+pw+12, py+ph//2), f"{total_xp:,} XP",
              font=_f(_FONT_SB2, 17), fill=(155,160,205), anchor="lm")

    # ── XP bar section ───────────────────────────────────────────────────────
    sec_y  = PAD + ROW1_H + 6
    pct    = int((xp_progress / xp_needed) * 100) if xp_needed > 0 else 100
    draw.text((PAD, sec_y), f"Progress to Level {level+1}",
              font=_f(_FONT_REG2, 16), fill=(80, 86, 128))
    bar_y = sec_y + 22
    bar_w = W - PAD*2
    bar_h = 16
    _progress_bar(draw, PAD, bar_y, bar_w, bar_h, pct, accent)
    xp_y  = bar_y + bar_h + 6
    draw.text((PAD, xp_y), f"{xp_progress:,} / {xp_needed:,} XP",
              font=_f(_FONT_REG2, 15), fill=(100,106,155))
    draw.text((W-PAD, xp_y), f"{pct}%",
              font=_f(_FONT_BOLD2, 15), fill=accent_l, anchor="ra")

    # ── Stat cards (two rows of 3) ────────────────────────────────────────────
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

    st_y0   = sec_y + BAR_SEC
    st_cols = 3
    st_gap  = 6
    st_w    = (W - PAD*2 - st_gap*(st_cols-1)) // st_cols

    for i, (lbl, val) in enumerate(stats):
        col  = i % st_cols
        row  = i // st_cols
        sx   = PAD + col*(st_w + st_gap)
        sy   = st_y0 + row*(STAT_H + st_gap)
        _rr(draw, [sx, sy, sx+st_w, sy+STAT_H], 10,
            fill=(12,15,31), outline=(28,34,72), width=2)
        draw.rounded_rectangle([sx+3, sy+3, sx+st_w-3, sy+8], radius=2, fill=(r,g,b))
        fs = 24 if len(str(val)) <= 9 else 18
        draw.text((sx+st_w//2, sy+STAT_H//2 - 8), str(val),
                  font=_f(_FONT_BOLD2, fs), fill=(238,242,255), anchor="mm")
        draw.text((sx+st_w//2, sy+STAT_H - 12), lbl,
                  font=_f(_FONT_BOLD2, 13), fill=(105,112,162), anchor="mm")

    # ── VC Partners ───────────────────────────────────────────────────────────
    part_y = st_y0 + STAT_H*2 + st_gap + 10
    _rr(draw, [PAD, part_y, W-PAD, part_y+PART_H], 10,
        fill=(11,14,28), outline=(28,34,72), width=2)
    draw.text((W//2, part_y+16), "TOP VC PARTNERS",
              font=_f(_FONT_BOLD2, 16), fill=accent_l, anchor="mm")
    draw.line([(PAD+10, part_y+26), (W-PAD-10, part_y+26)], fill=(28,34,72), width=1)

    if vc_partners:
        mc_list = [accent, (170,180,205), (180,115,62)]
        cw = (W - PAD*2) // 3
        for i, (pn, pt_) in enumerate(vc_partners[:3]):
            cx = PAD + i*cw + cw//2
            mc = mc_list[i]
            draw.text((cx, part_y+42), ["1ST","2ND","3RD"][i],
                      font=_f(_FONT_BOLD2, 14), fill=mc, anchor="mm")
            pn_d = pn[:13] + ("…" if len(pn)>13 else "")
            draw.text((cx, part_y+66), pn_d,
                      font=_f(_FONT_SB2, 20), fill=(222,228,255), anchor="mm")
            draw.text((cx, part_y+92), pt_,
                      font=_f(_FONT_LIGHT2, 15), fill=(92,97,138), anchor="mm")
    else:
        draw.text((W//2, part_y+PART_H//2), "No VC data yet",
                  font=_f(_FONT_LIGHT2, 17), fill=(58,63,95), anchor="mm")

    # ── Bottom row: Avg VC | Longest | Fav Game ──────────────────────────────
    bot_y = part_y + PART_H + 10
    bw3   = (W - PAD*2 - st_gap*2) // 3

    cells = [
        ("AVG DAILY VC",    avg_daily_vc,      ""),
        ("LONGEST SESSION", longest_session,   longest_session_date or ""),
        ("FAVORITE GAME",   favorite_game or "—", favorite_game_time if favorite_game else ""),
    ]

    for i, (lbl, val, sub) in enumerate(cells):
        cx = PAD + i*(bw3 + st_gap)
        _rr(draw, [cx, bot_y, cx+bw3, bot_y+BOTTOM_H], 10,
            fill=(11,14,28), outline=(28,34,72), width=2)
        draw.text((cx+bw3//2, bot_y+14), lbl,
                  font=_f(_FONT_BOLD2, 12), fill=(88,94,136), anchor="mm")
        vfs = 18 if len(str(val)) <= 12 else 14
        draw.text((cx+bw3//2, bot_y+BOTTOM_H//2+4), str(val),
                  font=_f(_FONT_BOLD2, vfs), fill=(232,236,255), anchor="mm")
        if sub:
            draw.text((cx+bw3//2, bot_y+BOTTOM_H-12), sub,
                      font=_f(_FONT_REG2, 12), fill=(72,77,115), anchor="mm")

    # Footer
    draw.text((W-PAD, H-8), f"⚡ {response_ms}",
              font=_f(_FONT_LIGHT2, 12), fill=(48,53,82), anchor="ra")

    # Export
    out = Image.new("RGB", (W, H), (9, 11, 20))
    out.paste(img, mask=img.split()[3])
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()