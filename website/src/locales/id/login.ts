import type en from "../en/login";
import type { Translation } from "../types";

const login: Translation<typeof en> = {
  title: "Masuk",
  intro: "Pilih pengguna yang ingin Anda gunakan.",
  note: "Nantinya masuk akan lewat gateway Blibli. Pilihan pengguna ini hanya untuk pengembangan.",
  loadingUsers: "Memuat pengguna…",
  loadError: "Gagal memuat pengguna",
  noUsers: {
    title: "Belum ada pengguna",
    text: "Tambahkan pengguna ke tabel app_user dulu (lihat backend/database/seeds/app_user.sql).",
  },
  user: "Pengguna",
  pickUser: "Pilih pengguna",
  continue: "Lanjut",
  notFound: {
    text: "Alamatnya mungkin salah ketik, atau halamannya sudah tidak ada.",
    home: "Ke beranda",
  },
};

export default login;
