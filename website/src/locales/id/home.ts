import type en from "../en/home";
import type { Translation } from "../types";

const home: Translation<typeof en> = {
  greeting: {
    morning: "Selamat pagi, {{name}}",
    midday: "Selamat siang, {{name}}",
    afternoon: "Selamat sore, {{name}}",
    evening: "Selamat malam, {{name}}",
  },
  subtitle: "Periksa reimbursement yang dikirim sistem lain, beserta hasil baca OCR pada setiap file struk.",
  loadingReports: "Memuat laporan…",
  loadError: "Gagal memuat laporan",
  empty: {
    title: "Belum ada reimbursement",
    text: "Sistem lain mengirimnya ke API reimbursement (POST /api/reimbursements). Laporan muncul di sini setelah diterima.",
  },
  clear: {
    eyebrow: "Semua sudah beres",
    title: "Tidak ada laporan yang perlu direview",
    processing_one: "OCR masih membaca {{count}} laporan. Jika ada yang perlu reviewer, laporan itu akan muncul di sini.",
    processing_other: "OCR masih membaca {{count}} laporan. Jika ada yang perlu reviewer, laporan itu akan muncul di sini.",
    done: "Semua laporan sudah disetujui atau ditolak: tidak ada lagi yang perlu diputuskan.",
  },
  attention: {
    eyebrow: "Perlu review Anda",
    title_one: "laporan perlu direview",
    title_other: "laporan perlu direview",
    receivedIn: "Diterima",
    chipTitle: "Laporan yang diterima pada {{month}} dan perlu direview",
    moreMonths_one: "+{{count}} bulan lainnya",
    moreMonths_other: "+{{count}} bulan lainnya",
    moreMonthsTitle: "Semua laporan yang perlu direview, dari yang terlama",
    start: "Mulai review",
    oldestFrom: "Dari yang terlama, mulai {{code}}",
    seeList: "Lihat dalam daftar",
  },
  bbm: {
    subtitle: "Reimbursement bahan bakar",
    open: "Buka laporan BBM",
    loading: "Memuat laporan BBM…",
    reports: "Laporan",
    submitted: "Diajukan",
    approved: "Disetujui",
    approvedAmount: "{{amount}} disetujui",
    of: " dari {{total}}",
    byStatus: "Laporan per status",
    byMonth: "Per bulan diterima",
    thisMonth: "Bulan ini",
    olderMonths_one: "{{count}} bulan sebelumnya:",
    olderMonths_other: "{{count}} bulan sebelumnya:",
    pickOnList: "pilih di daftar BBM",
  },
  month: {
    needReview_one: "{{count}} perlu direview",
    needReview_other: "{{count}} perlu direview",
    processing: "{{count}} diproses",
    clear: "Tidak ada yang perlu direview",
  },
};

export default home;
