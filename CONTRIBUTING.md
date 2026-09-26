# Berkontribusi ke fr (Ayesh)

Terima kasih sudah mau berkontribusi! Proyek ini adalah orkestrator multi-agent AI berbahasa Indonesia. Baca `AGENTS.md` (developer) dan `PANDUAN.md` (pengguna) sebelum mulai.

## Cara berkontribusi

1. **Fork** repo, buat branch dari `master`: `git checkout -b fitur/nama-fitur`.
2. Ikuti konvensi di bawah, lalu buka **Pull Request** ke `master` dengan deskripsi jelas (masalah → solusi → cara tes).
3. Untuk perubahan besar, buka **Issue** atau **Discussion** dulu agar disepakati.

## Yang bisa dikerjakan

- Perbaiki bug, tambah tes, perbaiki dokumentasi.
- Tambah skill (`.ayesh/skills/*.md`), aturan (`.ayesh/rules/*.md`), atau dokumen RAG (`data/*.txt`, lalu re-ingest).
- Usulkan fitur lewat Issue `feature request` atau diskusi ide.

## Aturan kode

- Python 3.11+, gaya kode mengikuti file yang ada (tanpa formatter wajib).
- **Jangan commit secrets**: `.env`, `*.pem`, `*.key`, `*.db` sudah di-`.gitignore`. Cek `git status` sebelum commit.
- **Jangan commit artefak**: `setup-fr.exe`, `dist/`, `build/`, `faiss_index/`, `tests/last_eval.json`, `tests/ab_results.json`, `strix_runs/`.
- Jaga **keyword hygiene** routing: jangan tambah kata generik (`sekarang`, `waktu`, `jam`) sebagai keyword agent — terbukti membajak follow-up ke agent yang salah (lihat `AGENTS.md`).
- Prompt (`config/rules.py`, `mcp_core/registry.py`, `mcp_core/skills.py`, `.ayesh/`) harus tetap memuat blok `## Identitas` Ayesh.
- Perubahan skema DB wajib lewat **Alembic** (`alembic revision --autogenerate`), bukan `create_all` manual — kecuali bootstrap awal via `bootstrap.py`.
- Satu PR = satu topik. Jangan campur refactor besar dengan fitur.

## Tes wajib sebelum PR

```bash
# Cepat, tanpa LLM/infra — wajib lolos tiap ubah prompt (717 tes):
python -m unittest discover -s tests

# End-to-end 29 kasus (butuh PG + Redis + LLM):
python -m tests.run_eval
# Opt-in LLM-as-judge:
python -m tests.run_eval --judge
```

PR dengan tes merah tidak akan di-merge. Bila 2 tes `TestNativeTools` gagal lokal, cek `LLM_PROVIDER` di `.env` Anda (tes itu butuh provider `google`).

## Menjalankan lokal

```bash
pip install -r requirements.txt
cp .env.example .env   # lalu isi API key
python bootstrap.py --check-only
python api_server.py
```

Butuh PostgreSQL + Redis lokal (lihat `PANDUAN.md` bagian Kebutuhan Sistem).

## Melapor bug / minta fitur

Gunakan template Issue yang tersedia (bug report / feature request). Sertakan: langkah reproduksi, log relevan (sensor API key!), versi Python, dan `LLM_PROVIDER` yang dipakai.

## Donasi & sponsor

Lihat tombol **Sponsor** di halaman repo atau `.github/FUNDING.yml`. Setiap dukungan dipakai untuk biaya API LLM eval & infrastruktur. Terima kasih!
