"""Vidro quente da Haimiya (estilo Aurora).

O Tkinter nao sabe fazer transparencia nem blur, por isso o aspeto e'
desenhado com Pillow: um fundo quente muito desfocado ocupa a janela e
cada superficie e' um recorte desse fundo, desfocado e com um veu branco
por cima. E' exatamente assim que o vidro fosco da referencia funciona.
"""
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


def fundo(l, a):
    """Fundo quente muito desfocado (vermelho, laranja e dourado)."""
    img = Image.new("RGB", (l, a), (56, 3, 16))
    d = ImageDraw.Draw(img)
    for (x0, y0, x1, y1), cor in (
        ((-0.20, -0.20, 0.50, 0.50), (240, 85, 25)),
        ((0.35, -0.30, 1.15, 0.35), (255, 165, 35)),
        ((0.45, 0.30, 1.30, 1.05), (235, 30, 55)),
        ((-0.20, 0.45, 0.50, 1.25), (195, 12, 85)),
        ((0.20, 0.55, 0.85, 1.30), (255, 120, 20)),
        ((0.62, 0.05, 1.15, 0.65), (255, 200, 60)),
        ((-0.10, 0.85, 0.75, 1.40), (150, 8, 45)),
        ((0.75, 0.70, 1.35, 1.35), (210, 25, 40)),
    ):
        d.ellipse([x0 * l, y0 * a, x1 * l, y1 * a], fill=cor)
    img = img.filter(ImageFilter.GaussianBlur(max(l, a) // 9))
    # depois do blur tudo fica uniforme: devolve contraste e sabor
    img = ImageEnhance.Contrast(img).enhance(1.20)
    img = ImageEnhance.Color(img).enhance(1.30)
    # escurece levemente para o texto branco aguentar por cima
    img = img.convert("RGBA")
    img.alpha_composite(Image.new("RGBA", (l, a), (16, 0, 5, 74)))
    # cantos da propria janela arredondados: a Windows torna transparente
    # tudo o que fique com a cor chave. A Tk compara o RGB (ignora o alfa),
    # por isso la' fora temos de escrever exatamente essa cor; o alfa 0
    # fica por fora tambem, para sistemas que aceitem os dois.
    m = Image.new("L", (l * 2, a * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, l * 2 - 1, a * 2 - 1], 36, fill=255)
    m = m.resize((l, a), Image.LANCZOS)
    binaria = m.point(lambda v: 255 if v >= 128 else 0)
    img = img.convert("RGB")
    img.paste(Image.new("RGB", (l, a), (13, 13, 20)), (0, 0), binaria.point(
        lambda v: 255 - v))
    img = img.convert("RGBA")
    img.putalpha(m)
    return img


def frescor(base, caixa, raio=24, veu=(255, 255, 255, 26),
            borda=(255, 255, 255, 54), sombra=120, desfoque=7):
    """Recorta `base` na `caixa`, desfoca, põe veu, canto arredondado,
    filete e sombra. Devolve uma imagem com folga para a sombra."""
    x0, y0, x1, y1 = (int(v) for v in caixa)
    w, h = x1 - x0, y1 - y0
    rec = base.crop((x0, y0, x1, y1)).convert("RGBA")
    if desfoque:
        rec = rec.filter(ImageFilter.GaussianBlur(desfoque))
    if veu:
        rec.alpha_composite(Image.new("RGBA", rec.size, veu))

    mascara = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mascara).rounded_rectangle([0, 0, w - 1, h - 1], raio, fill=255)
    rec.putalpha(mascara)

    # brilho fino no topo, como no original
    brilho = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(brilho).line([(raio, 1), (w - raio, 1)], fill=(255, 255, 255, 90), width=1)
    rec.alpha_composite(brilho)

    fio = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(fio).rounded_rectangle([0, 0, w - 1, h - 1], raio, outline=borda, width=1)
    rec.alpha_composite(fio)

    folga = 26
    saida = Image.new("RGBA", (w + folga * 2, h + folga * 2), (0, 0, 0, 0))
    if sombra:
        s = Image.new("RGBA", saida.size, (0, 0, 0, 0))
        ImageDraw.Draw(s).rounded_rectangle(
            [folga, folga + 7, folga + w, folga + h], raio, fill=(0, 0, 0, sombra))
        saida.alpha_composite(s.filter(ImageFilter.GaussianBlur(15)))
    saida.alpha_composite(rec, (folga, folga))
    return saida


def pilula(base, caixa, raio=16, veu=(255, 255, 255, 34),
           borda=(255, 255, 255, 64), cor=None, desfoque=5):
    """Superficie pequena (pilula ou botao) exatamente na caixa dada,
    sem folga — desenha-se por cima da imagem ja montada."""
    x0, y0, x1, y1 = (int(v) for v in caixa)
    w, h = x1 - x0, y1 - y0
    rec = base.crop((x0, y0, x1, y1)).convert("RGBA")
    if desfoque:
        rec = rec.filter(ImageFilter.GaussianBlur(desfoque))
    if cor:
        rec.alpha_composite(Image.new("RGBA", rec.size, cor))
    elif veu:
        rec.alpha_composite(Image.new("RGBA", rec.size, veu))

    mascara = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mascara).rounded_rectangle([0, 0, w - 1, h - 1], raio, fill=255)
    rec.putalpha(mascara)

    fio = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(fio).rounded_rectangle([0, 0, w - 1, h - 1], raio, outline=borda, width=1)
    rec.alpha_composite(fio)
    return rec


def divisor(img, x, y0, y1, cor=(255, 255, 255, 44)):
    """Fio vertical fino (separador da barra lateral)."""
    fio = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(fio).line([(x, y0), (x, y1)], fill=cor, width=1)
    img.alpha_composite(fio)


def amostra(img, x, y):
    """Cor hex do ponto (x, y) — fundo aproximado de um widget, usado
    so' ate a imagem exata estar aplicada (evita um relampago preto)."""
    if img.mode != "RGB":
        img = img.convert("RGB")
    x = max(0, min(img.width - 1, int(x)))
    y = max(0, min(img.height - 1, int(y)))
    r, g, b = img.getpixel((x, y))
    return "#%02x%02x%02x" % (r, g, b)
