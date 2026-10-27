import type en from "../en/bbmList";
import type { Translation } from "../types";

const bbmList: Translation<typeof en> = {
  title: "Reimbursement BBM",
  subtitle: "Reimbursement bahan bakar yang dikirim sistem lain, dicocokkan dengan hasil baca OCR pada file struknya.",
  month: {
    label: "Diterima",
    all: "Semua bulan ({{count}})",
  },
  loading: "Memuat laporan…",
  loadError: "Gagal memuat laporan",
  search: {
    label: "Cari kode, nama, atau nomor karyawan",
    queue: "Pencarian “{{text}}”",
  },
  allReports: "Semua laporan",
  everyPage: "semua halaman",
  range: {
    paged_one: "{{from}}–{{to}} dari {{count}} laporan",
    paged_other: "{{from}}–{{to}} dari {{count}} laporan",
    pagedMatching_one: "{{from}}–{{to}} dari {{count}} laporan yang cocok",
    pagedMatching_other: "{{from}}–{{to}} dari {{count}} laporan yang cocok",
    filtered_one: "{{shown}} dari {{count}} laporan",
    filtered_other: "{{shown}} dari {{count}} laporan",
  },
  filters: {
    label: "Filter menurut status",
    receivedIn: "Diterima pada {{month}}",
    every: "Seluruh laporan BBM",
    parts: "{{status}}: bagian mana",
  },
  partHints: {
    duplicate:
      "Struk di setiap laporan ini juga diklaim di laporan yang diterima lebih dulu: file yang sama, atau struk " +
      "karyawan yang sama dengan tanggal, total, dan volume yang sama. Buka laporannya untuk membandingkan keduanya: " +
      "tolak jika struknya diklaim dua kali, setujui jika ternyata struknya berbeda.",
    proceed:
      "OCR menyetujui laporan ini karena menilai setiap perbedaannya sebagai salah baca. Periksa beberapa secara " +
      "acak: jika ada perbedaan yang memang tidak sesuai, buka laporannya lalu tolak.",
    failed:
      "Claude tidak bisa memberikan hasil baca file-file ini (waktu habis, gagal berjalan, atau jawabannya tidak bisa " +
      "dipakai), jadi tidak ada yang dibandingkan: ini tidak menunjukkan apa pun tentang struknya. Ulangi OCR untuk " +
      "semuanya (atau untuk satu laporan, dari halaman laporannya), atau cocokkan sendiri file dengan data yang disubmit.",
  },
  pages: "Halaman laporan",
  table: {
    caption: "Laporan reimbursement BBM",
    report: "Laporan",
    employee: "Karyawan",
    received: "Diterima",
    total: "Total",
    differences: "Perbedaan",
    status: "Status",
    open: "Buka",
  },
  empty: {
    none: "Belum ada reimbursement BBM",
    noneText: "Sistem lain mengirimnya ke API reimbursement (POST /api/reimbursements).",
    month: "Tidak ada laporan yang diterima pada {{month}}",
    monthText: "Pilih bulan lain, atau tampilkan laporan dari semua bulan.",
    showAllMonths: "Tampilkan semua bulan",
    noMatch: "Tidak ada laporan yang cocok",
    showAllOf: "Tampilkan semua laporan {{month}}",
    showAll: "Tampilkan semua laporan",
  },
  noMatch: {
    search: "Tidak ada yang cocok dengan “{{text}}”.",
    searchIn: "Tidak ada yang cocok dengan “{{text}}” di {{where}}.",
    status: "Saat ini tidak ada laporan dengan status ini.",
    statusIn: "Tidak ada laporan yang diterima pada {{month}} dengan status ini.",
  },
  report: {
    files: "{{count}} file",
    by: "Oleh {{name}}",
    byOcrProceed: "Oleh OCR: hanya salah baca",
    byOcrMatched: "Oleh OCR: sesuai",
    doubleClaim: "Struk sudah pernah diklaim",
  },
  ocr: {
    label: "OCR:",
    processing: "OCR: diproses",
    failed: "OCR: gagal membaca",
    same: "OCR: sama",
    less: "Hasil baca OCR {{amount}} lebih rendah daripada yang disubmit",
    more: "Hasil baca OCR {{amount}} lebih tinggi daripada yang disubmit",
  },
  differences: {
    notYet: "Belum dibandingkan",
    notCompared: "Tidak dibandingkan",
    none: "Tidak ada",
    count_one: "{{count}} perbedaan pada {{field}}",
    count_other: "{{count}} perbedaan pada {{field}}",
  },
  export: {
    button: "Ekspor ke Excel",
    exporting: "Mengekspor…",
    none: "Tidak ada laporan untuk diekspor",
    hint_one:
      "Unduh laporan di daftar ini{{scope}} sebagai file Excel: satu baris per struk, data yang disubmit di samping " +
      "hasil baca OCR.",
    hint_other:
      "Unduh {{count}} laporan di daftar ini{{scope}} sebagai file Excel: satu baris per struk, data yang disubmit di " +
      "samping hasil baca OCR.",
    tooMany: "Terlalu banyak laporan untuk diekspor",
    tooManyText: "Ekspor maksimal {{max}} laporan sekaligus. Pilih bulan atau status untuk mempersingkat daftar.",
    exported_one: "{{count}} laporan diekspor",
    exported_other: "{{count}} laporan diekspor",
    changed: "Daftar berubah sejak dimuat (tadinya {{shown}} laporan). Daftar sudah dimuat ulang. File: {{file}}",
    done_one: "{{count}} laporan diekspor ke Excel",
    done_other: "{{count}} laporan diekspor ke Excel",
    nothing: "Tidak ada yang diekspor",
    nothingText: "Laporan-laporan ini berubah sejak daftar dimuat. Daftar sudah dimuat ulang.",
    failed: "Gagal mengekspor ke Excel",
  },
  retry: {
    button: "Ulangi OCR",
    all: "Ulangi OCR ({{count}} laporan)",
    retrying: "Mengulang…",
    hint_one: "Ulangi OCR untuk laporan di daftar ini{{scope}}",
    hint_other: "Ulangi OCR untuk {{count}} laporan di daftar ini{{scope}}",
    title: "Ulangi OCR untuk {{code}}?",
    titleCount_one: "Ulangi OCR untuk {{count}} laporan?",
    titleCount_other: "Ulangi OCR untuk {{count}} laporan?",
    text:
      "File struknya masuk lagi ke antrean OCR. Claude membacanya ulang, biasanya dalam 15 sampai 35 detik, dan " +
      "sampai saat itu laporan ini berstatus Diproses.",
    textAll:
      "File struk dari {{count}} laporan di daftar ini{{scope}} masuk lagi ke antrean OCR. Claude membacanya ulang " +
      "satu per satu, biasanya 15 sampai 35 detik per file, dan sampai saat itu laporan-laporan ini berstatus Diproses.",
    stillFails: "Jika Claude tetap tidak bisa membaca sebuah file, laporannya kembali ke daftar ini.",
    failed: "OCR gagal diulang",
    queued_one: "Mengulang OCR untuk {{count}} laporan",
    queued_other: "Mengulang OCR untuk {{count}} laporan",
    queuedText: "Laporan berstatus Diproses sampai OCR selesai membacanya.",
    skipped_one: "{{count}} laporan sudah diulang atau diputuskan sebelumnya, jadi dibiarkan apa adanya.",
    skipped_other: "{{count}} laporan sudah diulang atau diputuskan sebelumnya, jadi dibiarkan apa adanya.",
    showProcessing: "Lihat yang diproses",
    nothing: "Tidak ada yang perlu diulang",
    nothingText: "{{error}} Daftar sudah dimuat ulang.",
  },
};

export default bbmList;
