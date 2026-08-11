import mysql.connector
from config import settings
import bcrypt


def init():
    # 1. Connect without DB to create it if needed
    conn = mysql.connector.connect(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD
    )
    cursor = conn.cursor()
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {settings.MYSQL_DB}")
    conn.commit()
    cursor.close()
    conn.close()

    # 2. Connect to the database and create tables
    conn = mysql.connector.connect(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB
    )
    cursor = conn.cursor()

    # ------------------------------------------------------------------ #
    #  Core tables – use CREATE IF NOT EXISTS to preserve existing data   #
    # ------------------------------------------------------------------ #
    create_statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            username     VARCHAR(50)  UNIQUE NOT NULL,
            email        VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role         VARCHAR(20)  NOT NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS students (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            usn          VARCHAR(100) UNIQUE NOT NULL,
            name         VARCHAR(100) NOT NULL,
            source_file  VARCHAR(255)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS marks (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            usn          VARCHAR(100) NOT NULL,
            semester     INT,
            sgpa         DECIMAL(4,2),
            cgpa         DECIMAL(4,2),
            year         INT,
            source_file  VARCHAR(255),
            FOREIGN KEY (usn) REFERENCES students(usn) ON DELETE CASCADE,
            UNIQUE KEY uq_usn_sem (usn, semester)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS security_logs (
            log_id         INT AUTO_INCREMENT PRIMARY KEY,
            user_role      VARCHAR(20),
            attempted_query TEXT NOT NULL,
            reason         TEXT NOT NULL,
            timestamp      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS query_history (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            user_role       VARCHAR(20),
            natural_query   TEXT NOT NULL,
            generated_query TEXT,
            execution_time  FLOAT,
            timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            filename      VARCHAR(255) UNIQUE,
            content_type  VARCHAR(100),
            file_type     VARCHAR(20),
            size_bytes    INT,
            uploaded_by   VARCHAR(50),
            uploaded_at   DATETIME,
            db_status     VARCHAR(20),
            row_count     INT,
            students_saved INT,
            marks_saved   INT
        )
        """,
    ]

    for stmt in create_statements:
        try:
            cursor.execute(stmt)
        except Exception as e:
            print(f"Create/check error: {e}")

    # Default users
    cursor.execute("SELECT id FROM users WHERE username='admin'")
    if not cursor.fetchone():
        pwd_hash = bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode()
        cursor.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (%s,%s,%s,%s)",
            ('admin', 'admin@college.edu', pwd_hash, 'Admin')
        )

    cursor.execute("SELECT id FROM users WHERE username='staff'")
    if not cursor.fetchone():
        pwd_hash = bcrypt.hashpw(b'staff123', bcrypt.gensalt()).decode()
        cursor.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (%s,%s,%s,%s)",
            ('staff', 'staff@college.edu', pwd_hash, 'Staff')
        )

    conn.commit()
    cursor.close()
    conn.close()
    print("MySQL database and tables initialized successfully.")


if __name__ == "__main__":
    init()
