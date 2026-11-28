/** Run phone auth SQL on DATABASE_URL (Liara shell: node scripts/apply-phone-migrations.cjs). */
const fs = require("fs");
const path = require("path");
const { Pool } = require("pg");

const FILES = ["0010_user_phone.sql", "0011_phone_otp.sql"];

async function main() {
  const url = process.env.DATABASE_URL;
  if (!url) {
    console.error("DATABASE_URL is not set");
    process.exit(1);
  }
  const dir = path.join(__dirname, "..", "db", "migrations");
  const pool = new Pool({ connectionString: url });
  try {
    for (const name of FILES) {
      const file = path.join(dir, name);
      const sql = fs.readFileSync(file, "utf8");
      process.stdout.write(`Applying ${name}... `);
      await pool.query(sql);
      process.stdout.write("OK\n");
    }
    const check = await pool.query(
      `SELECT to_regclass('public.phone_otp_challenges') IS NOT NULL AS ok`,
    );
    console.log("phone_otp_challenges:", check.rows[0]?.ok);
  } finally {
    await pool.end();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});