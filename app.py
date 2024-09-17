from flask import Flask, request, render_template, redirect, url_for, session, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from jobs1 import recommend_jobs
import pandas as pd

app = Flask(__name__)

# Flask secret key for sessions
app.secret_key = 'your_secret_key'

# Database file location for SQLite
DATABASE_FILE = "placement.db"

def create_db_connection():
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        return conn
    except Exception as e:
        print("Database connection failed due to {}".format(e))
        return None

def create_userinfo_table():
    conn = create_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS userinfo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    experience INTEGER NOT NULL,
                    designation TEXT NOT NULL,
                    skills TEXT NOT NULL
                );
            """)
            conn.commit()
        except Exception as e:
            print("Error creating userinfo table: ", e)
        finally:
            cur.close()
            conn.close()

def create_recommendations_table():
    conn = create_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS recommendations (
                    rec_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    job_id INTEGER NOT NULL,
                    company_id INTEGER NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES userinfo(id),
                    FOREIGN KEY (company_id) REFERENCES companies(company_id)
                );
            """)
            conn.commit()
        except Exception as e:
            print("Error creating recommendations table: ", e)
        finally:
            cur.close()
            conn.close()

@app.route('/')
@app.route('/welcome')
def welcome():
    return render_template('welcome.html')

@app.route('/choice')
def choice():
    return render_template('choice.html')
# Function to retrieve candidate data from the database
def get_candidates():
    conn = create_db_connection()
    if conn:
        cursor = conn.cursor()
        query = 'SELECT id, name, email, experience, designation, skills FROM userinfo'
        cursor.execute(query)
        candidates_info = cursor.fetchall()
        conn.close()
        return candidates_info
    return []

@app.route('/recommendations')
def recommendations():
    candidates_info = get_candidates()
    return render_template('candidates.html', candidates_info=candidates_info)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Ensure all fields are provided
        if not username or not password:
            return render_template('login.html', error='missing_fields')

        conn = create_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT password, name, email, experience, designation, skills FROM userinfo WHERE username = ?", (username,))
            user = cur.fetchone()

            if user is None:
                return render_template('login.html', error='username_not_found')
            elif user[0] != password:
                return render_template('login.html', error='incorrect_password')
            elif user:
                session['username'] = username  # Store username in session
                # Pass user details to viewprofile.html
                return redirect(url_for('view_profile', username=username))
            cur.close()
            conn.close()

    return render_template('login.html')

@app.route('/logout')
def logout():
    # Clear the user session
    session.clear()
    # Redirect to login page
    return redirect(url_for('welcome'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        name = request.form['name']
        email = request.form['email']
        experience = request.form['experience']
        designation = request.form['designation']
        skills = request.form['skills']

        # hashed_password = generate_password_hash(password, method='sha256')

        conn = create_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                # Check if username exists
                cur.execute("SELECT id FROM userinfo WHERE username = ?", (username,))
                if cur.fetchone():
                    return render_template('signup.html', error="username_exists")
                # Insert new user if username does not exist
                cur.execute("""
                    INSERT INTO userinfo (username, password, name, email, experience, designation, skills)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                """, (username, password, name, email, experience, designation, skills))
                user_id = cur.lastrowid
                conn.commit()
                session['user_id'] = user_id
                session['username'] = username  # Store username in session
                return redirect(url_for('view_profile', username=username))
            except Exception as e:
                print(f"Error signing up: {e}")
            finally:
                cur.close()
                conn.close()
    return render_template('signup.html')

@app.route('/view_profile/<username>')
def view_profile(username):
    conn = create_db_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT username, name, email, experience, designation, skills FROM userinfo WHERE username = ?", (username,))
        user_details = cur.fetchone()
        if user_details:
            return render_template('viewprofile.html', username=user_details[0], name=user_details[1], email=user_details[2], experience=user_details[3], designation=user_details[4], skills=user_details[5])
        else:
            # Handle case where user details are not found
            return redirect(url_for('signup'))

@app.route('/recommend_jobs')
def recommend_jobs_route():
    username = session.get('username')
    if not username:
        return redirect(url_for('login'))

    skills = request.args.get('skills')
    designation = request.args.get('designation')
    experience = request.args.get('experience')
    experience = int(experience) if experience and experience.isdigit() else 0

    recommendations = recommend_jobs(skills, designation, experience)

    conn = create_db_connection()
    if conn and recommendations:
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM userinfo WHERE username = ?", (username,))
            user_id_row = cur.fetchone()
            user_id = user_id_row[0] if user_id_row else None

            for job in recommendations:
                company_id = job.get('company id')
                job_id = int(job.get('job id'))  # Ensure job_id is an integer
                if company_id:
                    try:
                        cur.execute("SELECT company, domain FROM companies WHERE company_id = ?", (company_id,))
                        company_info = cur.fetchone()
                        if company_info:
                            job['Company'] = company_info[0]
                            job['Domain'] = company_info[1]
                    except Exception as e:
                        print(f"Database query failed due to: {e}")

                if user_id and company_id:
                    cur.execute("""
                        SELECT rec_id FROM recommendations
                        WHERE user_id = ? AND job_id = ? AND company_id = ?;
                    """, (user_id, job_id, company_id))
                    if not cur.fetchone():
                        try:
                            cur.execute("""
                                INSERT INTO recommendations (user_id, job_id, company_id)
                                VALUES (?, ?, ?);
                            """, (user_id, job_id, company_id))
                        except Exception as e:
                            print(f"Failed to insert recommendation due to: {e}")
                            conn.rollback()

            conn.commit()
        except Exception as e:
            print(f"Error processing recommendations: {e}")
            conn.rollback()
        finally:
            cur.close()
            conn.close()

    if not recommendations:
        recommendations = [{"message": "No recommendations found!"}]

    return render_template('recommendations.html', recommendations=recommendations, username=username)

@app.route('/recruiter_login', methods=['GET', 'POST'])
def recruiter_login():
    if request.method == 'POST':
        company_id = request.form.get('companyid')
        company_password = request.form.get('companypassword')

        # Ensure all fields are provided
        if not company_id or not company_password:
            return render_template('recruiter_login.html', error='missing_fields')

        conn = create_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT company_pwd, company, domain FROM companies WHERE company_id = ?", (company_id,))
            company_info = cur.fetchone()
            if company_info is None:
                # Alert if the company ID does not exist
                return render_template('recruiter_login.html', error='id_not_found')
            elif company_password != company_info[0]:
                # Alert if the password is incorrect for the given company ID
                return render_template('recruiter_login.html', error='incorrect_password')
            else:
                # Assuming you want to store the company ID in the session like the username in the user login
                session['company_id'] = company_id
                session['company'] = company_info[1]  # Storing company name
                session['domain'] = company_info[2]  # Storing domain
                # Redirect to recruiter's dashboard or appropriate page after successful login
                return redirect(url_for('dashboard'))
    return render_template('recruiter_login.html')

@app.route('/dashboard')
def dashboard():
    # Fetch company name and domain from session
    company = session.get('company')
    domain = session.get('domain')
    return render_template('dashboard.html', company=company, domain=domain)

@app.route('/job_postings')
def job_postings():
    company = session.get('company')
    company_id = session.get('company_id')  # Assuming company_id is stored in the session
    if not company_id:
        # Redirect to login if not authenticated
        return redirect(url_for('recruiter_login'))

    try:
        # Read the CSV file
        df = pd.read_csv('jobs_info.csv')

        # Filter the DataFrame for jobs matching the logged-in company
        company_jobs = df[df['company id'] == int(company_id)]  # Ensure company_id is an integer

        # Convert the filtered DataFrame to a list of dictionaries
        job_postings = company_jobs.to_dict('records')
    except FileNotFoundError:
        # Handle case where file is missing
        return "Error: Jobs info file not found.", 404
    except Exception as e:
        # Handle other potential errors
        return f"Error: {str(e)}", 500

    return render_template('job_postings.html', jobs=job_postings, company=company)



# def execute_sql_from_file(conn, sql_file_path):
#     try:
#         if conn is None:
#             raise ValueError("Database connection is not established.")
        
#         cursor = conn.cursor()
        
#         # Read the SQL commands from the file
#         with open(sql_file_path, 'r') as file:
#             sql_commands = file.read()

#         # Execute the SQL commands
#         cursor.executescript(sql_commands)
        
#         # Commit changes
#         conn.commit()
#     except Exception as e:
#         print(f"An error occurred: {e}")
#     finally:
#         if conn:
#             conn.close()

# # Example usage
# conn = create_db_connection()
# sql_file_path = 'companies_table.txt'
# execute_sql_from_file(conn, sql_file_path)

if __name__ == '__main__':
    create_userinfo_table()
    create_recommendations_table()
    app.run(debug=True)