---
name: presentasi
description: "Buat presentasi interaktif dengan reveal.js atau Marp. Trigger: /presentasi, /slides, /ppt, /buat-ppt, /presentasi-html, /presentasi-markdown"
category: office
tags: [presentation, slides, revealjs, marp, ppt]
---

# Presentasi (HTML Slides & Markdown Slides)

Buat presentasi interaktif menggunakan **reveal.js** (HTML) atau **Marp** (Markdown). Keduanya menghasilkan presentasi web yang profesional.

## Reveal.js (HTML)

### Langkah
```
"Buat presentasi produk dengan reveal.js"
"Buat slides tech talk dengan code highlighting"
```

### Menggunakan office_tool
```
office_tool("create_pptx", '{"output": "presentasi.pptx", "slides": [{"title": "Slide 1", "content": "Konten slide 1"}, {"title": "Slide 2", "content": "Konten slide 2"}]}')
```

### Dasar Structure

```html
<!doctype html>
<html>
<head>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4/dist/reveal.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4/dist/theme/black.css">
</head>
<body>
    <div class="reveal">
        <div class="slides">
            <section>Slide 1</section>
            <section>Slide 2</section>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/reveal.js@4/dist/reveal.js"></script>
    <script>Reveal.initialize();</script>
</body>
</html>
```

### Themes
`black`, `white`, `league`, `beige`, `sky`, `night`, `serif`, `simple`, `solarized`, `blood`, `moon`

### Transitions
```javascript
Reveal.initialize({
    transition: 'slide',  // none, fade, slide, convex, concave, zoom
    transitionSpeed: 'default'
});
```

### Fragments (Animasi)

```html
<section>
    <p class="fragment">Muncul pertama</p>
    <p class="fragment fade-in">Lalu ini</p>
    <p class="fragment highlight-red">Highlight merah</p>
</section>
```

Fragment styles: `fade-in`, `fade-out`, `fade-up`, `fade-down`, `fade-left`, `fade-right`, `highlight-red`, `highlight-blue`, `highlight-green`, `strike`

### Code Highlighting

```html
<section>
    <pre><code data-trim data-line-numbers="1|3-4">
def hello():
    print("Halo")
    print("Dunia")
    return True
    </code></pre>
</section>
```

### Speaker Notes

```html
<section>
    <h2>Judul Slide</h2>
    <p>Konten</p>
    <aside class="notes">
        Catatan presenter. Tekan 'S' untuk melihat.
    </aside>
</section>
```

### Backgrounds

```python
# Warna
<section data-background-color="#4d7e65">

# Gambar
<section data-background-image="image.jpg" data-background-size="cover">

# Gradient
<section data-background-gradient="linear-gradient(to bottom, #283b95, #17b2c3)">
```

### Config

```javascript
Reveal.initialize({
    controls: true,
    progress: true,
    slideNumber: true,
    hash: true,
    center: true,
    width: 960,
    height: 700,
    plugins: [RevealMarkdown, RevealHighlight, RevealNotes]
});
```

## Marp (Markdown)

### Langkah
```
"Buat presentasi dari markdown ini"
"Convert catatan saya jadi presentasi"
```

### Basic Syntax

```markdown
---
marp: true
---

# Slide Pertama

Konten di sini

---

# Slide Kedua

- Point 1
- Point 2
```

### Themes
```yaml
---
marp: true
theme: default  # default, gaia, uncover
---
```

### Directives

```yaml
---
marp: true
theme: gaia
class: lead        # Centered title
paginate: true     # Nomor halaman
header: 'Header'
footer: 'Footer'
backgroundColor: #fff
---
```

### Gambar

```markdown
![width:500px](gambar.png)
![bg](background.jpg)
![bg left:40%](sidebar.jpg)
```

### Kolom

```markdown
<div class="columns">
<div>

## Kiri

Konten

</div>
<div>

## Kanan

Konten

</div>
</div>
```

### Export

```bash
# Install Marp CLI
npm install -g @marp-team/marp-cli

# Export ke PDF
marp slides.md -o presentasi.pdf

# Export ke PPTX
marp slides.md -o presentasi.pptx

# Export ke HTML
marp slides.md -o presentasi.html
```

## Contoh: Tech Talk (Reveal.js)

```html
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <title>API Design Best Practices</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4/dist/reveal.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4/dist/theme/night.css">
</head>
<body>
    <div class="reveal">
        <div class="slides">
            <section data-background-gradient="linear-gradient(to bottom right, #1a1a2e, #16213e)">
                <h1>API Design</h1>
                <h3>Best Practices 2026</h3>
            </section>
            <section>
                <h2>Agenda</h2>
                <ol>
                    <li class="fragment">RESTful Principles</li>
                    <li class="fragment">Authentication</li>
                    <li class="fragment">Error Handling</li>
                </ol>
            </section>
            <section>
                <h2>Questions?</h2>
            </section>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/reveal.js@4/dist/reveal.js"></script>
    <script>Reveal.initialize({ hash: true });</script>
</body>
</html>
```

## Contoh: Presentasi (Marp)

```markdown
---
marp: true
theme: gaia
paginate: true
---

<!-- _class: lead -->

# Update Proyek

Q4 2026 Review

---

# Highlights

- Revenue: +25%
- Users: +50%
- NPS: 72

---

# Roadmap

| Q1 | Q2 | Q3 | Q4 |
|----|----|----|-----|
| MVP | Beta | Launch | Scale |

---

<!-- _class: lead -->

# Terima Kasih!

questions@company.com
```

## Tips
- Reveal.js: gunakan `data-auto-animate` untuk animasi smooth
- Marp: gunakan `<!-- _class: lead -->` untuk slide judul
- Keduanya support speaker notes (Reveal.js: tekan S, Marp: gunakan `<!-- ... -->`)
- Export ke PDF untuk distribusi

## Limitasi
- Reveal.js: perlu browser untuk melihat
- Marp: butuh Marp CLI untuk export
- Keduanya: animasi complex terbatas dibanding PowerPoint native
- Font tergantung yang tersedia di sistem
