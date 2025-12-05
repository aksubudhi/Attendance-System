"""
User Setup Script - Create admin and regular users for CCTV Attendance System
Usage: python3 setup_users.py
"""

import psycopg2
import bcrypt
import getpass
import re
from config import settings

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    return True, "Password is strong"

def validate_username(username):
    """Validate username format"""
    if len(username) < 3 or len(username) > 50:
        return False, "Username must be between 3 and 50 characters"
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        return False, "Username can only contain letters, numbers, hyphens, and underscores"
    return True, "Username is valid"

def hash_password(password):
    """Hash password using bcrypt"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def display_header():
    """Display welcome header"""
    print("=" * 70)
    print("CCTV Attendance System - User Setup")
    print("=" * 70)
    print("\nManage user accounts for the system.")
    print("You can create admin, manager, or regular users.\n")

def show_main_menu():
    """Show main menu"""
    print("\n" + "─" * 70)
    print("MAIN MENU")
    print("─" * 70)
    print("1. Create new user")
    print("2. List all users")
    print("3. Exit")
    print("─" * 70)
    return input("Select option (1-3): ").strip()

def create_user(cursor, conn):
    """Create a new user"""
    print("\n" + "─" * 70)
    print("CREATE NEW USER")
    print("─" * 70)
    
    # Get username
    while True:
        username = input("\nEnter username (3-50 characters, alphanumeric, -, _): ").strip()
        is_valid, message = validate_username(username)
        
        if not is_valid:
            print(f"❌ {message}")
            continue
        
        # Check if username exists
        cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            print("❌ Username already exists")
            continue
        
        break
    
    # Get full name
    while True:
        full_name = input("Enter full name: ").strip()
        if len(full_name) < 2:
            print("❌ Full name is required (minimum 2 characters)")
            continue
        break
    
    # Get email
    while True:
        email = input("Enter email address: ").strip().lower()
        if not validate_email(email):
            print("❌ Invalid email format")
            continue
        
        # Check if email exists
        cursor.execute("SELECT email FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            print("❌ Email already registered")
            continue
        
        break
    
    # Get role
    print("\nSelect user role:")
    print("1. admin   - Full system access, can start/stop cameras")
    print("2. manager - Can view reports and manage employees")
    print("3. user    - View-only access to dashboard")
    
    while True:
        role_choice = input("\nSelect role (1-3): ").strip()
        if role_choice == '1':
            role = 'admin'
            break
        elif role_choice == '2':
            role = 'manager'
            break
        elif role_choice == '3':
            role = 'user'
            break
        else:
            print("❌ Invalid selection")
    
    # Get password
    print("\nPassword Requirements:")
    print("  • At least 8 characters long")
    print("  • At least one uppercase letter")
    print("  • At least one lowercase letter")
    print("  • At least one number")
    print("  • At least one special character (!@#$%^&*...)")
    
    while True:
        password = getpass.getpass("\nEnter password: ")
        is_valid, message = validate_password(password)
        
        if not is_valid:
            print(f"❌ {message}")
            continue
        
        password_confirm = getpass.getpass("Confirm password: ")
        
        if password != password_confirm:
            print("❌ Passwords do not match")
            continue
        
        break
    
    # Review and confirm
    print("\n" + "─" * 70)
    print("REVIEW USER DETAILS")
    print("─" * 70)
    print(f"Username:  {username}")
    print(f"Full Name: {full_name}")
    print(f"Email:     {email}")
    print(f"Role:      {role}")
    
    role_descriptions = {
        'admin': 'Full access - Can start/stop cameras, manage all users',
        'manager': 'Manager access - Can manage employees and view reports',
        'user': 'Limited access - Can only view dashboard'
    }
    print(f"Permissions: {role_descriptions[role]}")
    print("─" * 70)
    
    confirm = input("\nCreate this user account? (yes/no): ").lower()
    
    if confirm != 'yes':
        print("❌ User creation cancelled")
        return False
    
    # Hash password and insert user
    print("\nCreating user account...")
    password_hash = hash_password(password)
    
    try:
        # FIXED: Changed NOW() to CURRENT_TIMESTAMP for PostgreSQL
        cursor.execute("""
            INSERT INTO users 
            (username, password_hash, full_name, email, role, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s, TRUE, CURRENT_TIMESTAMP)
        """, (username, password_hash, full_name, email, role))
        
        conn.commit()
        
        print("\n" + "=" * 70)
        print("USER CREATED SUCCESSFULLY!")
        print("=" * 70)
        print(f"\nUsername: {username}")
        print(f"Role:     {role}")
        print(f"Status:   Active")
        print("\nThe user can now login at: http://localhost:5173/login")
        print("=" * 70)
        
        return True
    
    except psycopg2.Error as e:
        print(f"\nDatabase error: {e}")
        conn.rollback()  # Added rollback on error
        return False

def list_users(cursor):
    """List all users"""
    print("\n" + "─" * 70)
    print("ALL USERS")
    print("─" * 70)
    
    try:
        cursor.execute("""
            SELECT id, username, full_name, email, role, is_active, created_at, last_login
            FROM users
            ORDER BY created_at DESC
        """)
        
        users = cursor.fetchall()
        
        if not users:
            print("No users found in the system.")
            return
        
        print(f"\n{'ID':<4} {'Username':<15} {'Full Name':<20} {'Email':<25} {'Role':<10} {'Status':<10}")
        print("─" * 90)
        
        for user in users:
            user_id, username, full_name, email, role, is_active, created_at, last_login = user
            status = "Active" if is_active else "Inactive"
            email_display = email[:25] if len(email) <= 25 else email[:22] + "..."
            full_name_display = full_name[:20] if len(full_name) <= 20 else full_name[:17] + "..."
            
            print(f"{user_id:<4} {username:<15} {full_name_display:<20} {email_display:<25} {role:<10} {status:<10}")
            
            if last_login:
                print(f"     Created: {created_at} | Last Login: {last_login}")
            else:
                print(f"     Created: {created_at} | Last Login: Never")
        
        print("─" * 90)
        print(f"\nTotal users: {len(users)}")
        print(f"Admins: {sum(1 for u in users if u[4] == 'admin')}")
        print(f"Managers: {sum(1 for u in users if u[4] == 'manager')}")
        print(f"Users: {sum(1 for u in users if u[4] == 'user')}")
        
    except psycopg2.Error as e:

        print(f"Database error: {e}")

def main():
    """Main function"""
    display_header()
    
    # Database connection
   
    # Database connection
    DB_CONFIG = {
        'host': settings.DB_HOST,
        'port': settings.DB_PORT,
        'user': settings.DB_USER,
        'password': settings.DB_PASSWORD,
        'database': settings.DB_NAME
    }


    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print("Database connected successfully!\n")
        
        # Check if users table has admin
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        admin_count = cursor.fetchone()[0]
        
        if admin_count == 0:
            print("WARNING: No admin user found in the system!")
            print("Please create at least one admin user.\n")
        
        # Main menu loop
        while True:
            choice = show_main_menu()
            
            if choice == '1':
                if create_user(cursor, conn):
                    response = input("\nCreate another user? (yes/no): ").lower()
                    if response != 'yes':
                        break
            
            elif choice == '2':
                list_users(cursor)
            
            elif choice == '3':
                print("\nExiting setup script...")
                break
            
            else:
                print("❌ Invalid selection")
        
        cursor.close()
        conn.close()
        
        print("\nSetup script completed.")
        
    except psycopg2.Error as e:

        print(f"Database error: {e}")
        print("\nPlease ensure:")
        print("  1. PostgreSQL is running")
        print(f"  2. Database '{settings.DB_NAME}' exists")
        print(f"  3. User '{settings.DB_USER}' has proper permissions")
        return
    except Exception as e:
        print(f"Error: {e}")
        return

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
