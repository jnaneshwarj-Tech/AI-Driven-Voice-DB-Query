-- ============================================================
-- College Student Database Schema (MySQL)
-- ============================================================

CREATE DATABASE IF NOT EXISTS college_mysql_db;
USE college_mysql_db;

CREATE TABLE IF NOT EXISTS students_personal (
    student_id   INT AUTO_INCREMENT PRIMARY KEY,
    usn          VARCHAR(20) UNIQUE NOT NULL,
    first_name   VARCHAR(50),
    last_name    VARCHAR(50),
    email        VARCHAR(100),
    phone        VARCHAR(20),
    address      TEXT,
    blood_group  VARCHAR(10),
    father_name  VARCHAR(100),
    mother_name  VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS students_academic (
    academic_id      INT AUTO_INCREMENT PRIMARY KEY,
    student_id       INT NOT NULL,
    department       VARCHAR(50),
    admission_year   INT,
    current_semester INT,
    FOREIGN KEY (student_id) REFERENCES students_personal(student_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS semester_gpa (
    gpa_id     INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    semester   INT NOT NULL,
    sgpa       DECIMAL(4,2),
    cgpa       DECIMAL(4,2),
    UNIQUE KEY uq_student_sem (student_id, semester),
    FOREIGN KEY (student_id) REFERENCES students_personal(student_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS marks (
    mark_id        INT AUTO_INCREMENT PRIMARY KEY,
    student_id     INT NOT NULL,
    semester       INT NOT NULL,
    subject_name   VARCHAR(100),
    internal_marks INT,
    external_marks INT,
    total_marks    INT,
    FOREIGN KEY (student_id) REFERENCES students_personal(student_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS users (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    username   VARCHAR(50) UNIQUE NOT NULL,
    email      VARCHAR(100) UNIQUE NOT NULL,
    password   VARCHAR(255) NOT NULL,
    role       ENUM('Admin','Staff') NOT NULL DEFAULT 'Admin',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS query_history (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    user_role      VARCHAR(20),
    natural_query  TEXT,
    generated_sql  TEXT,
    execution_time FLOAT,
    timestamp      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS security_logs (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    user_role      VARCHAR(20),
    attempted_sql  TEXT,
    reason         VARCHAR(255),
    timestamp      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Sample data
INSERT IGNORE INTO students_personal (usn, first_name, last_name, email, phone, address, blood_group, father_name, mother_name) VALUES
('4HG23CS032', 'Manoj', 'Kumar',  'manoj@college.edu', '9876543210', 'Bangalore', 'O+',  'Ramesh Kumar',  'Sunita Kumar'),
('4HG23CS033', 'Priya', 'Sharma', 'priya@college.edu', '9876543211', 'Mysore',    'A+',  'Suresh Sharma', 'Meena Sharma'),
('4HG23CS034', 'Rahul', 'Verma',  'rahul@college.edu', '9876543212', 'Hubli',     'B+',  'Vijay Verma',   'Anita Verma'),
('4HG23CS035', 'Sneha', 'Patil',  'sneha@college.edu', '9876543213', 'Belgaum',   'AB+', 'Anil Patil',    'Rekha Patil');

INSERT IGNORE INTO students_academic (student_id, department, admission_year, current_semester)
SELECT student_id, 'CSE', 2023, 3 FROM students_personal WHERE usn IN ('4HG23CS032','4HG23CS033','4HG23CS034','4HG23CS035');

INSERT IGNORE INTO semester_gpa (student_id, semester, sgpa, cgpa)
SELECT sp.student_id, v.semester, v.sgpa, v.cgpa
FROM students_personal sp
JOIN (
    SELECT '4HG23CS032' AS usn, 1 AS semester, 8.20 AS sgpa, 8.20 AS cgpa UNION ALL
    SELECT '4HG23CS032', 2, 8.50, 8.35 UNION ALL
    SELECT '4HG23CS032', 3, 8.80, 8.50 UNION ALL
    SELECT '4HG23CS033', 1, 7.90, 7.90 UNION ALL
    SELECT '4HG23CS033', 2, 8.10, 8.00 UNION ALL
    SELECT '4HG23CS034', 1, 8.60, 8.60 UNION ALL
    SELECT '4HG23CS034', 2, 8.90, 8.75 UNION ALL
    SELECT '4HG23CS035', 1, 7.50, 7.50 UNION ALL
    SELECT '4HG23CS035', 2, 7.80, 7.65
) v ON sp.usn = v.usn;

INSERT IGNORE INTO marks (student_id, semester, subject_name, internal_marks, external_marks, total_marks)
SELECT sp.student_id, v.semester, v.subject_name, v.internal_marks, v.external_marks, v.total_marks
FROM students_personal sp
JOIN (
    SELECT '4HG23CS032' AS usn, 3 AS semester, 'Data Structures'    AS subject_name, 18 AS internal_marks, 72 AS external_marks, 90 AS total_marks UNION ALL
    SELECT '4HG23CS032', 3, 'Database Management', 19, 75, 94 UNION ALL
    SELECT '4HG23CS032', 3, 'Operating Systems',   17, 68, 85 UNION ALL
    SELECT '4HG23CS033', 3, 'Data Structures',     16, 65, 81 UNION ALL
    SELECT '4HG23CS033', 3, 'Database Management', 18, 70, 88
) v ON sp.usn = v.usn;
