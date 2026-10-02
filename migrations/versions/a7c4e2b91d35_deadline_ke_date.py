"""deadline jadi kolom DATE

Revision ID: a7c4e2b91d35
Revises: ddd7e9fce307
Create Date: 2026-10-02 09:20:41.118204

Tenggat tugas sebelumnya disimpan sebagai String(10) berisi 'YYYY-MM-DD'.
Bentuknya selalu empat digit, jadi perbandingan leksikografis kebetulan
sama dengan perbandingan tanggal. Dua konsekuensinya:

1. Kolomnya TEXT, jadi database tidak tahu itu tanggal dan index di
   atasnya mengurutkan berdasarkan byte, bukan berdasarkan tanggal.
2. Sortir deadline dan query 'dalam N hari ke depan' bisa salah diam-diam
   kalau ada nilai yang tidak persis 'YYYY-MM-DD' masuk lewat jalur lain.

Kolom DATE membuat perbandingan dilakukan sebagai tanggal, dan PostgreSQL
benar-benar menolak format tanggal yang salah, bukan diam-diam menerima.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c4e2b91d35'
down_revision = 'ddd7e9fce307'
branch_labels = None
depends_on = None

# Kolom cadangan untuk menyimpan nilai lama sementara kolom aslinya
# diubah tipenya. Dihapus di akhir upgrade().
BACKUP = 'deadline_sementara'


def _sqlite_normalize(column):
    """SQL SQLite: ubah satu nilai teks jadi 'YYYY-MM-DD', atau NULL.

    Tanggal dengan satu digit terpotong diluruskan lebih dulu:

        '2026-10-1'  ->  '2026-10' + '-1'  ->  '2026-10-01'

    Kalau langsung strftime, SQLite menolak format satu digit dan
    nilainya jadi NULL, jadi tenggat yang sebenarnya terbaca hilang
    begitu saja. Nilai yang benar-benar tidak bisa diparse dibikin NULL:
    lebih baik tenggat hilang daripada data palsu.

    GLOB dipakai karena operator LIKE di SQLite '_' berarti satu karakter
    apa pun, sedangkan GLOB tidak punya arti khusus: pola ini cocok persis
    dengan deretan digit.
    """
    year = "substr({0}, 1, 4)".format(column)
    month = "substr({0}, 6, 2)".format(column)
    rest = "substr({0}, 6)".format(column)
    tail = "substr({0}, 9)".format(column)
    return (
        "CASE WHEN {year} GLOB '[0-9][0-9][0-9][0-9]' "
        "AND {month} GLOB '[0-9][0-9]' "
        "AND substr({rest}, 3, 1) = '-' "
        "AND ({tail} GLOB '[0-9][0-9]' OR {tail} GLOB '[0-9]') "
        "THEN {year} || '-' || {month} || '-' || "
        "substr('0' || ({tail} + 0), -2) "
        "END"
    ).format(year=year, month=month, rest=rest, tail=tail)


def _normalize(column):
    """SQL PostgreSQL: sama seperti di atas, pakai regexp.

    PostgreSQL punya regexp dan SUBSTRING, jadi GLOB dan +
    tidak ada. Dua database memang butuh SQL yang beda untuk
    normalisasi yang sama.
    """
    return (
        "CASE WHEN {col} ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{1,2}}$' "
        "THEN to_char(to_date({col}, 'YYYY-MM-DD'), 'YYYY-MM-DD') "
        "END"
    ).format(col=column)


def upgrade():
    """Ubah tipe kolom tanpa kehilangan satu baris pun.

    Ini lebih rumit dari seharusnya, dan alasannya khusus SQLite.

    SQLite tidak punya tipe DATE sungguhan. Untuk mengubah tipe kolom,
    Alembic memakai batch_alter_table: ia membuat tabel baru, menyalin
    data dengan INSERT INTO ... SELECT CAST(deadline AS DATE), lalu
    menukar tabelnya.

    CAST itu yang merusak data:

        CAST('2026-11-01' AS DATE)  ->  2026   (integer, bukan tanggal)

    SQLite memotong bagian numerik pertama, lalu membacanya sebagai hari
    Julian. Nilai aslinya sudah hilang saat itu juga, jadi tidak bisa
    dipulihkan sesudahnya: strftime('%Y-%m-%d', 2026) menghasilkan
    -4707-06-11, bukan 2026-11-01.

    Verifikasi langsung:

        INSERT INTO t (d) SELECT v FROM old           -> '2026-11-01'
        INSERT INTO t (d) SELECT CAST(v AS DATE)      -> 2026 (integer)

    Karena itu nilai lama disalin ke kolom cadangan lebih dulu, masih
    dalam bentuk teks, baru dipulihkan setelah kolomnya berubah.
    Kolom itulah salinan yang aman.
    """
    normalize = (
        _sqlite_normalize
        if op.get_bind().dialect.name == 'sqlite'
        else _normalize
    )

    # 1. Simpan nilai lama sebagai teks, sudah dinormalisasi.
    #
    #    Di PostgreSQL kolom DATE menyimpan DATE asli, jadi langkah
    #    normalisasi dan pemulihan sama sekali tidak perlu: alter_column
    #    sudah mengubah nilainya dengan benar, dan PostgreSQL menolak
    #    format yang salah dengan error, bukan diam-diam menerima.
    #    Jalur dua database di bawah hanya dipakai SQLite.
    sqlite = op.get_bind().dialect.name == 'sqlite'

    if sqlite:
        op.add_column('tasks', sa.Column(BACKUP, sa.String(10), nullable=True))
        op.execute(
            'UPDATE tasks SET {backup} = {normalized} WHERE deadline IS NOT NULL'
            .format(backup=BACKUP, normalized=normalize('deadline'))
        )
    else:
        # PostgreSQL tidak butuh kolom cadangan: cast-nya benar, bukan
        # merusak. Tapi varchar tidak bisa di-cast ke date secara
        # otomatis, jadi nilainya diluruskan di tempat lebih dulu.
        #
        # Ini penting untuk '2026-10-1'. Tanpa normalisasi, PostgreSQL
        # akan menolak cast-nya karena format itu bukan ISO yang dia
        # terima, dan migrasi berhenti dengan error. Dengan
        # normalisasi, tanggalnya jadi '2026-10-01' lalu cast-nya
        # berhasil.
        op.execute(
            'UPDATE tasks SET deadline = {normalized} WHERE deadline IS NOT NULL'
            .format(normalized=normalize('deadline'))
        )

    # 2. Ganti tipe kolom.
    #
    #    postgresql_using wajib ada di PostgreSQL: itu memberitahu cara
    #    konversinya, karena PostgreSQL menolak menebak sendiri. Tanpa
    #    itu migrasi berhenti dengan 'column deadline cannot be cast
    #    automatically to type date'.
    #
    #    Di SQLite langkah ini menyalin baris dengan CAST, dan di situlah
    #    nilainya rusak seperti dijelaskan di docstring fungsi ini.
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.alter_column(
            'deadline',
            existing_type=sa.String(length=10),
            type_=sa.Date(),
            existing_nullable=True,
            postgresql_using='deadline::date',
        )

    if op.get_bind().dialect.name == 'sqlite':
        # 3. Pulihkan dari cadangan, untuk SEMUA baris tanpa syarat.
        #
        #    Syaratnya tidak boleh `WHERE backup IS NOT NULL`. Baris
        #    yang gagal dinormalisasi punya backup NULL, tapi
        #    deadline-nya sudah dirusak CAST di langkah 2. Kalau
        #    baris itu dilewati, karanya tetap tertinggal di tabel:
        #    '2026-10-1' jadi integer 2026, 'bukan tanggal' jadi 0.
        #
        #    Kolom DATE di SQLite tetap menyimpan teks, dan itu
        #    perilaku standarnya: yang penting perbandingan dan
        #    index-nya benar.
        op.execute('UPDATE tasks SET deadline = {backup}'.format(backup=BACKUP))

        # 4. Buang kolom cadangan supaya skema sama persis dengan model.
        op.drop_column('tasks', BACKUP)


def downgrade():
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.alter_column(
            'deadline',
            existing_type=sa.Date(),
            type_=sa.String(length=10),
            existing_nullable=True,
        )
