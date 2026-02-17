import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import sqlite3
from passlib.hash import pbkdf2_sha256

DB_PATH = "workout_tracker.db"

# ---------- Database functions ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password_hash TEXT NOT NULL,
                  is_admin INTEGER DEFAULT 0)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS categories
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS exercises
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE,
                  description TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS exercise_categories
                 (exercise_id INTEGER,
                  category_id INTEGER,
                  FOREIGN KEY(exercise_id) REFERENCES exercises(id),
                  FOREIGN KEY(category_id) REFERENCES categories(id),
                  PRIMARY KEY (exercise_id, category_id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS sessions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  name TEXT NOT NULL,
                  date TEXT NOT NULL,
                  notes TEXT,
                  FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS workout_sets
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  session_id INTEGER NOT NULL,
                  exercise_id INTEGER NOT NULL,
                  weight REAL,
                  reps INTEGER,
                  set_number INTEGER,
                  rpe_rating INTEGER,
                  FOREIGN KEY(user_id) REFERENCES users(id),
                  FOREIGN KEY(session_id) REFERENCES sessions(id),
                  FOREIGN KEY(exercise_id) REFERENCES exercises(id))''')
    
    conn.commit()
    conn.close()

def upgrade_schema():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Check users table for profile columns
    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]
    if 'password_hash' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT ''")
        c.execute("UPDATE users SET password_hash = 'legacy'")
    
    # Add profile columns if missing
    profile_columns = ['age', 'weight_kg', 'height_cm', 'gender']
    for col in profile_columns:
        if col not in columns:
            if col == 'age':
                c.execute("ALTER TABLE users ADD COLUMN age INTEGER")
            elif col == 'weight_kg':
                c.execute("ALTER TABLE users ADD COLUMN weight_kg REAL")
            elif col == 'height_cm':
                c.execute("ALTER TABLE users ADD COLUMN height_cm REAL")
            elif col == 'gender':
                c.execute("ALTER TABLE users ADD COLUMN gender TEXT")
    
    # Check workout_sets table – rename column if needed
    c.execute("PRAGMA table_info(workout_sets)")
    columns = [col[1] for col in c.fetchall()]
    if 'rp_rating' in columns:
        c.execute("ALTER TABLE workout_sets RENAME COLUMN rp_rating TO rpe_rating")
    if 'session_id' not in columns:
        c.execute("ALTER TABLE workout_sets ADD COLUMN session_id INTEGER REFERENCES sessions(id)")
    if 'user_id' not in columns:
        c.execute("ALTER TABLE workout_sets ADD COLUMN user_id INTEGER REFERENCES users(id)")
    
    conn.commit()
    conn.close()

# ---------- Authentication ----------
def hash_password(password):
    return pbkdf2_sha256.hash(password)

def verify_password(password, hash):
    return pbkdf2_sha256.verify(password, hash)

def create_user(username, password, is_admin=0):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        password_hash = hash_password(password)
        c.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
                  (username, password_hash, is_admin))
        user_id = c.lastrowid
        conn.commit()
        return True, user_id
    except sqlite3.IntegrityError:
        return False, None
    finally:
        conn.close()

def authenticate_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, password_hash, is_admin FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    if row and verify_password(password, row[1]):
        return row[0], row[2]
    return None, None

def get_user_id(username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, is_admin FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    if row:
        return row[0], row[1]
    return None, None

# ---------- Profile functions ----------
def get_user_profile(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT age, weight_kg, height_cm, gender FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"age": row[0], "weight_kg": row[1], "height_cm": row[2], "gender": row[3]}
    return {"age": None, "weight_kg": None, "height_cm": None, "gender": None}

def update_user_profile(user_id, age, weight_kg, height_cm, gender):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''UPDATE users 
                 SET age = ?, weight_kg = ?, height_cm = ?, gender = ?
                 WHERE id = ?''',
              (age, weight_kg, height_cm, gender, user_id))
    conn.commit()
    conn.close()

# ---------- Categories ----------
def get_categories():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT id, name FROM categories ORDER BY name", conn)
    conn.close()
    return df

def add_category(name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

# ---------- Exercises ----------
def get_exercises(category_ids=None, search_term=""):
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT DISTINCT e.id, e.name, e.description
        FROM exercises e
        LEFT JOIN exercise_categories ec ON e.id = ec.exercise_id
        WHERE 1=1
    """
    params = []
    if category_ids:
        placeholders = ",".join("?" for _ in category_ids)
        query += f" AND ec.category_id IN ({placeholders})"
        params.extend(category_ids)
    if search_term:
        query += " AND e.name LIKE ?"
        params.append(f"%{search_term}%")
    query += " ORDER BY e.name"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def add_exercise(name, description, category_ids):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO exercises (name, description) VALUES (?, ?)", (name, description))
        exercise_id = c.lastrowid
        for cat_id in category_ids:
            c.execute("INSERT INTO exercise_categories (exercise_id, category_id) VALUES (?, ?)",
                      (exercise_id, cat_id))
        conn.commit()
    except sqlite3.IntegrityError:
        st.error("Exercise with this name already exists.")
    conn.close()

# ---------- Session functions ----------
def create_session(user_id, name, session_date, notes=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO sessions (user_id, name, date, notes) VALUES (?, ?, ?, ?)",
              (user_id, name, session_date.isoformat(), notes))
    session_id = c.lastrowid
    conn.commit()
    conn.close()
    return session_id

def get_user_sessions(user_id):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query('''SELECT id, name, date, notes 
                               FROM sessions 
                               WHERE user_id = ? 
                               ORDER BY date DESC, id DESC''', 
                           conn, params=(user_id,))
    conn.close()
    return df

def get_session_by_id(session_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, user_id, name, date, notes FROM sessions WHERE id = ?", (session_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "user_id": row[1], "name": row[2], "date": row[3], "notes": row[4]}
    return None

def delete_session(session_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM workout_sets WHERE session_id = ?", (session_id,))
    c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

# ---------- Workout Sets functions ----------
def log_set(user_id, session_id, exercise_id, weight, reps, set_number, rpe_rating):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO workout_sets 
                 (user_id, session_id, exercise_id, weight, reps, set_number, rpe_rating)
                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
              (user_id, session_id, exercise_id, weight, reps, set_number, rpe_rating))
    conn.commit()
    conn.close()

def get_user_workout_sets(user_id, exercise_id=None):
    conn = sqlite3.connect(DB_PATH)
    if exercise_id:
        df = pd.read_sql_query('''SELECT ws.*, e.name as exercise_name, s.name as session_name, s.date as session_date
                                   FROM workout_sets ws
                                   JOIN exercises e ON ws.exercise_id = e.id
                                   JOIN sessions s ON ws.session_id = s.id
                                   WHERE ws.user_id = ? AND ws.exercise_id = ? 
                                   ORDER BY s.date, ws.set_number''',
                               conn, params=(user_id, exercise_id))
    else:
        df = pd.read_sql_query('''SELECT ws.*, e.name as exercise_name, s.name as session_name, s.date as session_date
                                   FROM workout_sets ws
                                   JOIN exercises e ON ws.exercise_id = e.id
                                   JOIN sessions s ON ws.session_id = s.id
                                   WHERE ws.user_id = ? 
                                   ORDER BY s.date, e.name, ws.set_number''',
                               conn, params=(user_id,))
    conn.close()
    return df

def get_workout_sets_by_session(session_id):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query('''SELECT ws.*, e.name as exercise_name
                               FROM workout_sets ws
                               JOIN exercises e ON ws.exercise_id = e.id
                               WHERE ws.session_id = ?
                               ORDER BY e.name, ws.set_number''',
                           conn, params=(session_id,))
    conn.close()
    return df

def delete_workout_sets(set_ids):
    if not set_ids:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    placeholders = ",".join("?" for _ in set_ids)
    c.execute(f"DELETE FROM workout_sets WHERE id IN ({placeholders})", set_ids)
    conn.commit()
    conn.close()

# ---------- Streamlit App ----------
st.set_page_config(page_title="Power Scouter", layout="wide")

# Inject custom CSS for sidebar (background color #ff531b, image at top)
st.markdown("""
<style>
    /* Sidebar container */
    section[data-testid="stSidebar"] {
        background-color: #f7945b !important;
        padding-top: 0 !important;
    }
    /* Remove any extra top margin from the first element */
    section[data-testid="stSidebar"] > div:first-child {
        margin-top: 0 !important;
        padding-top: 0 !important;
    }
    /* Make all text and widget labels white for readability */
    section[data-testid="stSidebar"] * {
        color: #5d5d5d !important;
    }
    /* Style input fields and buttons for better visibility on orange */
    section[data-testid="stSidebar"] .stTextInput input,
    section[data-testid="stSidebar"] .stTextInput label,
    section[data-testid="stSidebar"] .stButton button {
        color: #5d5d5d !important;
    }
    /* Buttons keep their original orange (or you can customise) */
    section[data-testid="stSidebar"] .stButton button {
        background-color: #f48038 !important;
        border: none;
    }
    /* Optional: make the image stretch full width without extra spacing */
    section[data-testid="stSidebar"] img {
        margin-bottom: 1rem;
        width: 100%;
    }
    /* Sidebar text inputs with a lighter background */
    section[data-testid="stSidebar"] .stTextInput input {
        background-color: #f3fcff !important;   
        color: #5d5d5d !important;               
        border: none !important;
    }        

</style>
""", unsafe_allow_html=True)

init_db()
upgrade_schema()

default_cats = ["Legs", "Chest", "Core", "Back", "Shoulders", "Arms", "Full Body"]
for cat in default_cats:
    add_category(cat)

if "user_id" not in st.session_state:
    st.session_state.user_id = None
    st.session_state.username = ""
    st.session_state.is_admin = False
    st.session_state.auth_mode = "login"
    st.session_state.current_session_id = 0  # 0 means "Create new"
    st.session_state.workout_log = {}
    st.session_state.current_exercise = None
    st.session_state.bodyweight_toggle = False   # NEW: for set input

# Sidebar
with st.sidebar:
    # Top image
    st.image("assets/gk_s_top.jpg", width='stretch')

    if st.session_state.user_id is None:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Login", width='stretch'):
                st.session_state.auth_mode = "login"
        with col2:
            if st.button("Sign Up", width='stretch'):
                st.session_state.auth_mode = "signup"
        
        if st.session_state.auth_mode == "login":
            with st.form(key="login_form"):
                st.subheader("Login")
                username = st.text_input("Username", key="username_input")
                password = st.text_input("Password", type="password")
                login_button = st.form_submit_button("Log In")
                if login_button:
                    if username and password:
                        user_id, is_admin = authenticate_user(username, password)
                        if user_id:
                            st.session_state.user_id = user_id
                            st.session_state.username = username
                            st.session_state.is_admin = is_admin
                            st.session_state.current_session_id = 0
                            st.success("Login successful!")
                            st.rerun()
                        else:
                            st.error("Invalid username or password")
                    else:
                        st.error("Please enter username and password")
        else:
            with st.form(key="signup_form"):
                st.subheader("Sign Up")
                new_username = st.text_input("Username")
                new_password = st.text_input("Password", type="password")
                confirm_password = st.text_input("Confirm Password", type="password")
                signup_button = st.form_submit_button("Create Account")
                if signup_button:
                    if new_username and new_password:
                        if new_password != confirm_password:
                            st.error("Passwords do not match")
                        else:
                            existing_id, _ = get_user_id(new_username)
                            if existing_id:
                                st.error("Username already exists")
                            else:
                                success, user_id = create_user(new_username, new_password)
                                if success:
                                    st.success("Account created! Please log in.")
                                    st.session_state.auth_mode = "login"
                                    st.rerun()
                                else:
                                    st.error("Error creating account")
                    else:
                        st.error("Please fill all fields")
    else:
        st.write(f"Logged in as: **{st.session_state.username}**")

        # ---------- Profile expander ----------
        with st.expander("👤 My Profile"):
            profile = get_user_profile(st.session_state.user_id)
            with st.form("profile_form"):
                age = st.number_input("Age", min_value=0, max_value=120, value=profile['age'] or 30, step=1)
                weight_kg = st.number_input("Weight (kg)", min_value=0.0, max_value=300.0, value=profile['weight_kg'] or 70.0, step=0.5)
                height_cm = st.number_input("Height (cm)", min_value=0.0, max_value=250.0, value=profile['height_cm'] or 170.0, step=0.5)
                gender = st.selectbox("Gender", options=["Male", "Female", "Other"], index=["Male", "Female", "Other"].index(profile['gender']) if profile['gender'] in ["Male", "Female", "Other"] else 0)
                if st.form_submit_button("Save Profile"):
                    update_user_profile(st.session_state.user_id, age, weight_kg, height_cm, gender)
                    st.success("Profile updated!")
                    st.rerun()

        if st.button("Logout"):
            st.session_state.user_id = None
            st.session_state.username = ""
            st.session_state.is_admin = False
            st.session_state.current_session_id = 0
            st.session_state.workout_log = {}
            st.session_state.current_exercise = None
            st.session_state.bodyweight_toggle = False
            st.rerun()

if st.session_state.user_id is None:
    st.warning("Please log in using the sidebar.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["Log Workout", "Exercises", "Reports"])

# ----- Tab 1: Log Workout -----
with tab1:
    st.header("Log Your Workout")

    # Get user sessions
    sessions_df = get_user_sessions(st.session_state.user_id)
    session_options = {0: "➕ Create new session..."}
    if not sessions_df.empty:
        for _, row in sessions_df.iterrows():
            session_options[row['id']] = f"{row['date']} - {row['name']}"

    # --- Handle newly created session ---
    if "new_session_id" in st.session_state:
        st.session_state.current_session_id = st.session_state.new_session_id
        del st.session_state.new_session_id

    # --- Handle session reset after delete ---
    if "reset_to_new_session" in st.session_state and st.session_state.reset_to_new_session:
        st.session_state.current_session_id = 0
        del st.session_state.reset_to_new_session

    # Determine the index for the selectbox
    options_list = list(session_options.keys())
    if st.session_state.current_session_id in options_list:
        default_index = options_list.index(st.session_state.current_session_id)
    else:
        default_index = 0
        st.session_state.current_session_id = 0

    selected_session_id = st.selectbox(
        "Select Session",
        options=options_list,
        format_func=lambda x: session_options[x],
        index=default_index
    )

    # Update current session if user changed it manually
    if selected_session_id != st.session_state.current_session_id:
        st.session_state.current_session_id = selected_session_id
        # Reset per-exercise state when switching sessions
        st.session_state.workout_log = {}
        st.session_state.current_exercise = None
        st.session_state.bodyweight_toggle = False
        st.rerun()

    # ----- Create new session -----
    if st.session_state.current_session_id == 0:
        with st.form("new_session"):
            session_name = st.text_input("Session Name (e.g., 'Push Day A')")
            session_date = st.date_input("Session Date", value=date.today())
            session_notes = st.text_area("Notes (optional)")
            create_session_btn = st.form_submit_button("Create Session")
            if create_session_btn and session_name:
                new_id = create_session(st.session_state.user_id, session_name, session_date, session_notes)
                st.success(f"Session '{session_name}' created!")
                st.session_state.new_session_id = new_id
                st.session_state.workout_log = {}
                st.session_state.current_exercise = None
                st.session_state.bodyweight_toggle = False
                st.rerun()
        st.stop()  # Stop so the logging UI doesn't appear

    # ----- Logging interface for selected session -----
    session_info = get_session_by_id(st.session_state.current_session_id)
    st.subheader(f"Logging for: {session_info['date']} - {session_info['name']}")
    st.caption(session_info['notes'] if session_info['notes'] else "No notes")
    current_session_id = st.session_state.current_session_id

    # Delete workout button
    col1, col2 = st.columns([0.8, 0.2])
    with col2:
        if st.button("🗑️ Delete Workout", type="primary"):
            st.session_state.confirm_delete = current_session_id

    if "confirm_delete" in st.session_state and st.session_state.confirm_delete == current_session_id:
        st.warning("Are you sure? This will delete the entire workout and all its sets.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Yes, delete"):
                delete_session(current_session_id)
                st.success("Workout deleted.")
                st.session_state.reset_to_new_session = True
                st.session_state.pop("confirm_delete")
                st.session_state.workout_log = {}
                st.session_state.current_exercise = None
                st.session_state.bodyweight_toggle = False
                st.rerun()
        with col2:
            if st.button("Cancel"):
                st.session_state.pop("confirm_delete")
                st.rerun()

    # Exercise logging
    exercises_df = get_exercises()
    if exercises_df.empty:
        st.info("No exercises yet. Ask an admin to add some in the Exercises tab.")
    else:
        exercise_dict = exercises_df.set_index('id')['name'].to_dict()

        if "workout_log" not in st.session_state:
            st.session_state.workout_log = {}
            st.session_state.current_exercise = None
            st.session_state.bodyweight_toggle = False

        selected_exercise_id = st.selectbox("Add Exercise", options=list(exercise_dict.keys()),
                                            format_func=lambda x: exercise_dict[x],
                                            key="exercise_selector")

        # When exercise changes, reset bodyweight toggle and the sets list for that exercise? 
        # Actually we keep sets list per exercise, but bodyweight toggle is per-set input, so reset it.
        if st.session_state.current_exercise != selected_exercise_id:
            st.session_state.current_exercise = selected_exercise_id
            if selected_exercise_id not in st.session_state.workout_log:
                st.session_state.workout_log[selected_exercise_id] = []
            st.session_state.bodyweight_toggle = False   # Reset toggle when switching exercise
            st.rerun()

        st.write(f"**Sets for {exercise_dict[selected_exercise_id]}:**")
        sets_list = st.session_state.workout_log.get(selected_exercise_id, [])

        if sets_list:
            for i, (w, r, rpe) in enumerate(sets_list):
                st.text(f"Set {i+1}: {w} kg x {r} reps (RPE: {rpe})")

        # ---- NEW: Set input with bodyweight toggle ----
        col1, col2, col3, col4, col5 = st.columns([1.5,1.5,1.5,1,0.5])
        with col1:
            # Bodyweight toggle
            bodyweight = st.checkbox("Bodyweight?", value=st.session_state.bodyweight_toggle, key="bw_toggle")
            st.session_state.bodyweight_toggle = bodyweight

        with col2:
            # Added weight (if bodyweight on) or actual weight (if off)
            weight_label = "Added weight (kg)" if bodyweight else "Weight (kg)"
            added_weight = st.number_input(weight_label, min_value=0.0, step=2.5, key="new_weight")

        with col3:
            reps = st.number_input("Reps", min_value=1, step=1, key="new_reps")
        with col4:
            rpe = st.slider("RPE", 0, 10, 5, key="new_rpe")
        with col5:
            # "No weight" button – sets added_weight to 0
            if st.button("0", help="Set weight to 0"):
                # We can't directly modify the number_input's value from here, but we can store in session state
                st.session_state.new_weight = 0.0
                st.rerun()

        # Get profile weight for bodyweight calculation
        profile = get_user_profile(st.session_state.user_id)
        profile_weight = profile['weight_kg'] if profile['weight_kg'] is not None else 0.0

        # Calculate total weight for display
        if bodyweight:
            total_weight = profile_weight + added_weight
        else:
            total_weight = added_weight

        st.caption(f"Total resistance: {total_weight:.1f} kg")

        # Add set button
        col1, col2 = st.columns([4,1])
        with col2:
            if st.button("➕ Add Set", width='stretch'):
                if bodyweight and profile_weight == 0:
                    st.error("Please set your body weight in profile first.")
                elif reps <= 0:
                    st.error("Reps must be at least 1.")
                else:
                    sets_list.append((total_weight, reps, rpe))
                    st.session_state.workout_log[selected_exercise_id] = sets_list
                    # Reset toggle for next set? User might want to keep same setting; we'll keep as is.
                    st.rerun()

        # Duplicate and clear buttons
        if sets_list:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔁 Duplicate Last Set"):
                    last = sets_list[-1]
                    sets_list.append(last)
                    st.session_state.workout_log[selected_exercise_id] = sets_list
                    st.rerun()
            with col2:
                if st.button("🗑️ Clear Sets for This Exercise"):
                    st.session_state.workout_log[selected_exercise_id] = []
                    st.rerun()

        st.subheader("Current Session Summary")
        if st.session_state.workout_log:
            for ex_id, sets in st.session_state.workout_log.items():
                if sets:
                    st.write(f"**{exercise_dict[ex_id]}:** {len(sets)} sets")
        else:
            st.info("No sets added yet.")

        if st.button("💾 Save Entire Workout"):
            if not st.session_state.workout_log:
                st.warning("No sets to save.")
            else:
                user_id = st.session_state.user_id
                for ex_id, sets in st.session_state.workout_log.items():
                    for set_num, (w, r, rpe) in enumerate(sets, start=1):
                        log_set(user_id, current_session_id, ex_id, w, r, set_num, rpe)
                st.success("Workout saved!")
                st.session_state.workout_log = {}
                st.session_state.current_exercise = None
                st.session_state.bodyweight_toggle = False
                st.rerun()

# ----- Tab 2: Exercises (unchanged) -----
with tab2:
    st.header("Manage Exercises")
    
    if st.session_state.is_admin:
        with st.expander("Add New Exercise (Admin only)"):
            with st.form("new_exercise"):
                ex_name = st.text_input("Exercise Name")
                ex_desc = st.text_area("Description (optional)")
                categories_df = get_categories()
                if not categories_df.empty:
                    cat_options = categories_df['id'].tolist()
                    cat_labels = categories_df['name'].tolist()
                    selected_cats = st.multiselect("Categories", options=cat_options,
                                                   format_func=lambda x: cat_labels[cat_options.index(x)])
                else:
                    selected_cats = []
                    st.info("No categories available.")
                submitted = st.form_submit_button("Add Exercise")
                if submitted and ex_name:
                    add_exercise(ex_name, ex_desc, selected_cats)
                    st.success(f"Added {ex_name}")
                    st.rerun()
    else:
        st.info("Only admins can add new exercises.")
    
    st.subheader("Search Exercises")
    col1, col2 = st.columns(2)
    with col1:
        search_term = st.text_input("Search by name", "")
    with col2:
        categories_df = get_categories()
        if not categories_df.empty:
            cat_options = categories_df['id'].tolist()
            cat_labels = categories_df['name'].tolist()
            selected_cats_filter = st.multiselect("Filter by categories", options=cat_options,
                                                  format_func=lambda x: cat_labels[cat_options.index(x)])
        else:
            selected_cats_filter = []
    
    exercises_df = get_exercises(category_ids=selected_cats_filter if selected_cats_filter else None,
                                 search_term=search_term)
    if not exercises_df.empty:
        st.dataframe(exercises_df[['name', 'description']])
    else:
        st.info("No exercises found.")

# ----- Tab 3: Reports (updated with checkbox labels) -----
with tab3:
    st.header("Progress Reports")
    
    report_type = st.radio("View:", ["By Exercise", "By Workout Session"])
    
    if report_type == "By Exercise":
        user_id = st.session_state.user_id
        exercises_df = get_exercises()
        if exercises_df.empty:
            st.info("No exercises logged yet.")
        else:
            exercise_dict = exercises_df.set_index('id')['name'].to_dict()
            selected_exercise_id = st.selectbox("Select Exercise", options=list(exercise_dict.keys()),
                                                format_func=lambda x: exercise_dict[x], key="report_ex")
            
            data = get_user_workout_sets(user_id, selected_exercise_id)
            if data.empty:
                st.info("No data for this exercise.")
            else:
                # Calculate 1RM (Brzycki)
                data['1RM'] = data['weight'] * 36 / (37 - data['reps'])
                daily_max = data.groupby('session_date')['1RM'].max().reset_index()
                daily_max['session_date'] = pd.to_datetime(daily_max['session_date'])
                
                fig = px.line(daily_max, x='session_date', y='1RM', title='Estimated 1RM Progress')
                st.plotly_chart(fig, width='stretch')
                
                data['volume_load'] = data['weight'] * data['reps']
                daily_volume_load = data.groupby('session_date')['volume_load'].sum().reset_index()
                daily_volume_load['session_date'] = pd.to_datetime(daily_volume_load['session_date'])
                fig2 = px.bar(daily_volume_load, x='session_date', y='volume_load', title='Total Volume Load per Session')
                st.plotly_chart(fig2, width='stretch')
                
                st.subheader("Logged Sets")
                selected_indices = []
                for idx, row in data.iterrows():
                    col1, col2 = st.columns([0.1, 0.9])
                    with col1:
                        # Fixed: use non-empty label with label_visibility="collapsed"
                        if st.checkbox("Select", key=f"del_{row['id']}", label_visibility="collapsed"):
                            selected_indices.append(row['id'])
                    with col2:
                        st.write(f"**{row['session_date']}** - {row['exercise_name']}: {row['weight']} kg x {row['reps']} (Set {row['set_number']}, RPE:{row['rpe_rating']})")
                
                if selected_indices:
                    if st.button("Delete Selected Sets"):
                        delete_workout_sets(selected_indices)
                        st.success(f"Deleted {len(selected_indices)} set(s).")
                        st.rerun()
    
    else:  # By Workout Session
        st.subheader("Workout Sessions")
        user_id = st.session_state.user_id
        sessions_df = get_user_sessions(user_id)
        if sessions_df.empty:
            st.info("No sessions logged yet.")
        else:
            session_options = {}
            for _, row in sessions_df.iterrows():
                session_options[row['id']] = f"{row['date']} - {row['name']}"
            selected_session_id = st.selectbox("Select Session", options=list(session_options.keys()),
                                               format_func=lambda x: session_options[x])
            
            session_sets = get_workout_sets_by_session(selected_session_id)
            if session_sets.empty:
                st.info("No sets in this session.")
            else:
                session_info = get_session_by_id(selected_session_id)
                st.write(f"**Date:** {session_info['date']}")
                st.write(f"**Name:** {session_info['name']}")
                if session_info['notes']:
                    st.write(f"**Notes:** {session_info['notes']}")
                
                # Summary metrics
                total_volume_load = (session_sets['weight'] * session_sets['reps']).sum()
                total_sets = len(session_sets)
                total_reps = session_sets['reps'].sum()
                st.metric("Total Volume Load (kg)", f"{total_volume_load:.1f}")
                st.metric("Total Sets", total_sets)
                st.metric("Total Reps", total_reps)
                
                # Show sets grouped by exercise with detailed stats
                st.subheader("Exercise Details")
                for exercise_name, group in session_sets.groupby('exercise_name'):
                    st.write(f"**{exercise_name}**")
                    
                    # Calculate per-exercise stats
                    ex_sets = len(group)
                    ex_reps = group['reps'].sum()
                    ex_volume_load = (group['weight'] * group['reps']).sum()
                    ex_1rm = (group['weight'] * 36 / (37 - group['reps'])).max()  # max 1RM for the session
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Sets", ex_sets)
                    with col2:
                        st.metric("Total Reps", ex_reps)
                    with col3:
                        st.metric("Volume Load", f"{ex_volume_load:.1f} kg")
                    with col4:
                        st.metric("Est. 1RM", f"{ex_1rm:.1f} kg")
                    
                    # List individual sets
                    for _, row in group.iterrows():
                        st.write(f"  Set {row['set_number']}: {row['weight']} kg x {row['reps']} reps (RPE: {row['rpe_rating']})")
                
                # Delete sets from session
                st.subheader("Delete Sets")
                st.warning("Select sets to delete from this session:")
                selected_indices = []
                for idx, row in session_sets.iterrows():
                    col1, col2 = st.columns([0.1, 0.9])
                    with col1:
                        # Fixed: use non-empty label with label_visibility="collapsed"
                        if st.checkbox("Select", key=f"del_session_{row['id']}", label_visibility="collapsed"):
                            selected_indices.append(row['id'])
                    with col2:
                        st.write(f"{row['exercise_name']} - Set {row['set_number']}: {row['weight']} kg x {row['reps']} (RPE:{row['rpe_rating']})")
                
                if selected_indices:
                    if st.button("Delete Selected Sets from Session"):
                        delete_workout_sets(selected_indices)
                        st.success(f"Deleted {len(selected_indices)} set(s).")
                        st.rerun()