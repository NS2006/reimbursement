import type en from "../en/common";
import type { Translation } from "../types";

const common: Translation<typeof en> = {
  app: {
    name: "Reimbursement",
  },
  nav: {
    home: "Beranda",
    bbm: "BBM",
  },
  title: {
    home: "Beranda",
    bbm: "BBM",
    report: "{{code}} · BBM",
    notFound: "Halaman tidak ditemukan",
    signIn: "Masuk",
  },
  language: {
    label: "Bahasa",
    en: "English",
    id: "Bahasa Indonesia",
  },
  user: {
    switch: "Ganti pengguna",
  },
  actions: {
    refresh: "Muat ulang",
    refreshing: "Memuat ulang…",
    tryAgain: "Coba lagi",
    cancel: "Batal",
    close: "Tutup",
  },
  updatedAt: "Diperbarui {{time}}",
  reports_one: "{{count}} laporan",
  reports_other: "{{count}} laporan",
  reviewStatus: {
    needs_review: {
      label: "Perlu direview",
      hint: "Reviewer harus memutuskan",
      meaning: "Reviewer harus memeriksa file struk, lalu menyetujui atau menolak laporan ini.",
    },
    processing: {
      label: "Diproses",
      hint: "OCR sedang membacanya",
      meaning: "OCR sedang membaca file struk. Setelah terbaca, hasilnya langsung dibandingkan dengan data yang dikirim.",
    },
    approved: {
      label: "Disetujui",
      hint: "Oleh OCR atau reviewer",
      meaning: "Disetujui: struk sesuai, perbedaannya hanya salah baca OCR, atau reviewer menyetujuinya.",
    },
    rejected: {
      label: "Ditolak",
      hint: "Ditolak oleh reviewer",
      meaning: "Reviewer menolak laporan ini. Laporan yang sudah diperbaiki bisa dikirim lagi sebagai revisi baru.",
    },
  },
  ocrStatus: {
    needs_review: {
      label: "Perlu direview",
      hint: "Reviewer harus memeriksa file",
      meaning: "Reviewer harus memeriksa file struk: OCR menemukan perbedaan yang tidak bisa dijelaskannya.",
    },
    failed: {
      label: "OCR gagal membaca",
      hint: "Reviewer harus memeriksa file",
      meaning:
        "OCR tidak bisa membaca file struk, jadi tidak ada yang dibandingkan: reviewer harus mencocokkannya dengan data yang dikirim.",
    },
    processing: {
      label: "Diproses",
      hint: "OCR sedang membacanya",
      meaning: "OCR sedang membaca file struk. Setelah terbaca, hasilnya langsung dibandingkan dengan data yang dikirim.",
    },
    proceed: {
      label: "Proceed",
      hint: "Perbedaannya hanya salah baca OCR",
      meaning:
        "OCR menemukan perbedaan, tetapi semuanya salah baca OCR: angka lain di struk membuktikan nilai yang dikirim.",
    },
    matched: {
      label: "Sesuai",
      hint: "Struk sesuai",
      meaning: "File struk sesuai dengan data yang dikirim.",
    },
  },
  approvedBy: {
    matched: { label: "Sesuai", text: "Oleh OCR: struk sesuai" },
    proceed: { label: "Proceed", text: "Oleh OCR: hanya salah baca OCR" },
    reviewer: { label: "Oleh reviewer", text: "Oleh reviewer" },
  },
  needsReviewReason: {
    differences: {
      label: "Perbedaan",
      text: "OCR membaca file struk dan menemukan perbedaan yang tidak bisa dijelaskannya",
    },
    failed: { label: "OCR gagal membaca", text: "OCR tidak bisa membaca file struk, jadi tidak ada yang dibandingkan" },
  },
  statusParts: {
    needs_review: { label: "Semua yang perlu direview", text: "Setiap laporan yang perlu diputuskan reviewer" },
    approved: { label: "Semua yang disetujui", text: "Setiap laporan yang disetujui" },
  },
  statusBar: {
    empty: "Tidak ada laporan",
  },
  fields: {
    product_name: "Produk",
    date_of_expense: "Tanggal",
    price_per_liter: "Harga per liter",
    volume_liter: "Volume (L)",
    kilometer: "Kilometer",
    total_price: "Jumlah",
    discount: "Diskon",
    grand_total: "Grand total",
  },
  blue: {
    dismissAlert: "Tutup peringatan",
    close: "Tutup",
    previousPage: "Halaman sebelumnya",
    nextPage: "Halaman berikutnya",
    pages: "Halaman",
    mainNav: "Utama",
    breadcrumb: "Lokasi halaman",
    loading: "Memuat",
    notifications: "Notifikasi",
    closeNotification: "Tutup notifikasi",
    nothingToShow: "Tidak ada data.",
    remove: "Hapus",
  },
  errors: {
    unreachable: "Tidak bisa terhubung ke server. Periksa koneksi Anda, lalu coba lagi.",
    generic: "Terjadi kesalahan. Silakan coba lagi.",
    http: "Server menjawab dengan HTTP {{status}}.",
    invalidRequest: "Permintaan tidak valid. Muat ulang halaman, lalu coba lagi.",
    codes: {
      already_decided: "Laporan ini sudah diputuskan.",
      decided: "Laporan ini sudah diputuskan. Batalkan keputusannya untuk mengulang OCR.",
      decision_changed: "Keputusan laporan ini diubah orang lain. Periksa lagi sebelum memutuskan.",
      empty_list: "Tidak ada laporan di daftar ini.",
      file_missing: "File tidak ada di penyimpanan file.",
      file_storage_unavailable: "File tidak bisa dibaca saat ini. Coba lagi nanti.",
      internal_error: "Terjadi kesalahan di server.",
      invalid_based_on: "Keputusan di laporan ini berubah. Muat ulang halaman, lalu coba lagi.",
      invalid_description: "Komentar kosong atau terlalu panjang.",
      invalid_list: "Hanya daftar Perlu direview · OCR gagal membaca yang bisa diulang sekaligus.",
      invalid_q: "Pencarian maksimal 100 karakter.",
      invalid_reason: "Alasannya terlalu panjang.",
      invalid_user: "Pengguna tidak dikenal. Pilih pengguna lain.",
      not_comment_author: "Anda hanya bisa mengubah atau menghapus komentar Anda sendiri.",
      not_found: "Data tidak ditemukan.",
      nothing_failed: "OCR tidak lagi gagal pada laporan ini: laporan ini sudah diulang.",
      nothing_to_reopen: "Tidak ada keputusan di laporan ini yang bisa dibatalkan.",
      reason_required: "Tuliskan alasan laporan ini ditolak.",
      revision_changed: "Revisi baru laporan ini masuk. Periksa dulu sebelum memutuskan.",
      too_many_reports: "Daftar ini berisi lebih dari 5.000 laporan. Pilih satu bulan atau persempit pencarian.",
    },
  },
};

export default common;
