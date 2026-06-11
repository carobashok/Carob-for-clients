import streamlit as st
from utils.supabase_client import get_supabase


def login_page():
    """Render the login screen."""
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)

        # Logo / Title
        st.markdown("""
        <div style='text-align:center;padding:30px 20px 10px;background:#1F4E79;
                    border-radius:12px 12px 0 0;'>
            <h1 style='color:white;margin:0;font-size:36px;'>🎫 IT Help Desk</h1>
            <p style='color:#BDD7EE;margin:6px 0 0;font-size:14px;'>
                AI-Powered Support Management
            </p>
        </div>
        """, unsafe_allow_html=True)

        with st.container():
            st.markdown("""
            <div style='background:white;padding:30px;border-radius:0 0 12px 12px;
                        border:1px solid #ddd;border-top:none;'>
            </div>
            """, unsafe_allow_html=True)

            email    = st.text_input("📧 Email", placeholder="your@email.com")
            password = st.text_input("🔒 Password", type="password", placeholder="••••••••")

            col_a, col_b = st.columns(2)
            with col_a:
                login_btn = st.button("Login", use_container_width=True, type="primary")
            with col_b:
                signup_btn = st.button("Register", use_container_width=True)

            if login_btn:
                _do_login(email, password)

            if signup_btn:
                st.session_state["show_signup"] = True

        # Sign-up form
        if st.session_state.get("show_signup"):
            st.markdown("---")
            st.subheader("📝 Create Account")
            _signup_form()


def _do_login(email: str, password: str):
    if not email or not password:
        st.error("Please enter email and password.")
        return

    supabase = get_supabase()
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})

        if res.user:
            st.session_state["user"] = res.user
            st.session_state["session"] = res.session

            # Fetch profile
            profile_res = supabase.table("profiles").select(
                "*, departments(name), home:locations!profiles_home_location_id_fkey(name), "
                "agent_teams(name)"
            ).eq("id", res.user.id).single().execute()

            if profile_res.data:
                st.session_state["profile"] = profile_res.data
            else:
                st.error("Profile not found. Please contact your administrator.")
                logout()
                return

            st.success(f"Welcome back, {profile_res.data.get('full_name', '')}!")
            st.rerun()
        else:
            st.error("Invalid email or password.")

    except Exception as e:
        err = str(e)
        if "Invalid login credentials" in err:
            st.error("Invalid email or password.")
        elif "Email not confirmed" in err:
            st.warning("Please confirm your email before logging in.")
        else:
            st.error(f"Login failed: {err}")


def _signup_form():
    """Self-registration form for employees."""
    supabase = get_supabase()

    with st.form("signup_form"):
        full_name = st.text_input("Full Name *")
        email     = st.text_input("Email *")
        password  = st.text_input("Password *", type="password",
                                   help="Minimum 8 characters")
        password2 = st.text_input("Confirm Password *", type="password")
        emp_id    = st.text_input("Employee ID", placeholder="Optional")

        # Fetch departments and locations for dropdowns
        try:
            depts = supabase.table("departments").select("id, name").eq("is_active", True).execute()
            locs  = supabase.table("locations").select("id, name, code").eq("is_active", True).execute()

            dept_options = {d["name"]: d["id"] for d in depts.data} if depts.data else {}
            loc_options  = {f"{l['name']} ({l['code']})": l["id"] for l in locs.data} if locs.data else {}
        except:
            dept_options = {}
            loc_options  = {}

        dept_name = st.selectbox("Department *", ["-- Select --"] + list(dept_options.keys()))
        loc_name  = st.selectbox("Home Location *", ["-- Select --"] + list(loc_options.keys()))

        submitted = st.form_submit_button("Create Account", type="primary")

        if submitted:
            # Validations
            errors = []
            if not full_name:  errors.append("Full name is required.")
            if not email:      errors.append("Email is required.")
            if not password:   errors.append("Password is required.")
            if len(password) < 8: errors.append("Password must be at least 8 characters.")
            if password != password2: errors.append("Passwords do not match.")
            if dept_name == "-- Select --": errors.append("Please select a department.")
            if loc_name  == "-- Select --": errors.append("Please select a home location.")

            if errors:
                for e in errors:
                    st.error(e)
                return

            try:
                # Create auth user
                auth_res = supabase.auth.sign_up({
                    "email":    email,
                    "password": password,
                })

                if auth_res.user:
                    dept_id = dept_options[dept_name]
                    loc_id  = loc_options[loc_name]

                    # Insert profile
                    profile_data = {
                        "id":                   auth_res.user.id,
                        "full_name":            full_name,
                        "email":                email,
                        "role":                 "employee",
                        "employee_id":          emp_id if emp_id else None,
                        "department_id":        dept_id,
                        "home_location_id":     loc_id,
                        "current_location_id":  loc_id,
                    }
                    supabase.table("profiles").insert(profile_data).execute()

                    st.success("✅ Account created! Please check your email to confirm, then log in.")
                    st.session_state["show_signup"] = False
                else:
                    st.error("Registration failed. Please try again.")

            except Exception as e:
                err = str(e)
                if "already registered" in err or "already exists" in err:
                    st.error("This email is already registered. Please log in.")
                else:
                    st.error(f"Registration error: {err}")


def logout():
    """Clear session state and sign out."""
    try:
        supabase = get_supabase()
        supabase.auth.sign_out()
    except:
        pass

    for key in ["user", "session", "profile", "show_signup"]:
        st.session_state.pop(key, None)


def require_role(*roles):
    """Guard decorator — call at top of any page that needs role check."""
    profile = st.session_state.get("profile", {})
    role    = profile.get("role", "")
    if role not in roles:
        st.error("⛔ You don't have permission to view this page.")
        st.stop()


def get_current_profile():
    return st.session_state.get("profile", {})


def get_current_user_id():
    profile = st.session_state.get("profile", {})
    return profile.get("id")
