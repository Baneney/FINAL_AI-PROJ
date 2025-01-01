from flask import Flask, request, render_template, redirect, url_for, flash, session, jsonify
import firebase_admin
import os
from firebase_admin import credentials, db
from datetime import datetime, timedelta
from experta import KnowledgeEngine, Fact, Rule, P
# from stable_baselines3 import PPO
# import gym
# from gym import spaces
import numpy as np

# session['username'] = user_data['username']
# session['UserID'] = user_id
# session['user_ID'] = user_id

app = Flask(__name__)
app.secret_key = 'semluiz_123'

cred = credentials.Certificate(os.path.join(os.getcwd(), 'serviceAccountKey.json'))
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://ai-proj-appdev-default-rtdb.firebaseio.com/' 
})

db = firebase_admin.db 

@app.route('/') # SIGNIN-LANDING PAGE HTML
def home():
    return render_template('landingPage.html')


@app.route('/signUp')  # SIGN-UP HTML
def signUp():
    return render_template('signUp.html')


@app.route('/profile')  # PROFILE HTML
def profile():
    username = session.get('username')  # Get the logged-in user's username from the session
    if not username:
        flash("Please log in to view your profile.", "error")
        return redirect(url_for('home'))

    # Fetch user data from the database
    users_ref = db.reference('users')
    users = users_ref.get()

    # Find the logged-in user's data
    user_data = None
    for user_id, data in users.items():
        if data.get('username') == username:
            user_data = data
            session['user_ID'] = user_id
            session['current_pass'] = user_data['password']
            break

    if not user_data:
        flash("User data not found.", "error")
        return redirect(url_for('home'))
    

    # Pass user data to the profile template
    return render_template('profile.html', user=user_data)


@app.route('/updateEmail', methods=['POST']) # UPDATE EMAIL
def updateEmail():
    username = session.get('username')  # Get logged-in user's username from the session
    if not username:
        flash("Please log in to update your profile.", "error")
        return redirect(url_for('home'))


    new_email = request.form['UPDATE_EMAIL']

    # Retrieve and update the user data in the database
    users_ref = db.reference('users')
    users = users_ref.get()

    for user_id, data in users.items():
        if data.get('username') == username:
            users_ref.child(user_id).update({
                'email': new_email,
            })

            flash("Email updated successfully!", "success")
            return redirect(url_for('profile'))

    flash("An error occurred while updating your email.", "error")
    return redirect(url_for('profile'))


@app.route('/updatePassword', methods=['POST']) # UPDATE PASSWORD
def updatePassword():
    username = session.get('username') 

    curr_pass = request.form['CurrentPass']
    currPass = session.get('current_pass')
    new_pass1 = request.form['NewPass1']
    new_pass2 = request.form['NewPass2']
    
    if new_pass1 != new_pass2:
        flash("Passwords do not match!", "error")
        return redirect(url_for('profile')) 
    
    if curr_pass != currPass:
        flash("Current Password is incorect.", "error")
        return redirect(url_for('profile')) 

    # Retrieve and update the user data in the database
    users_ref = db.reference('users')
    users = users_ref.get()

    for user_id, data in users.items():
        if data.get('username') == username:
            users_ref.child(user_id).update({
                'password': new_pass1,
            })

            flash("Password updated successfully!", "success")
            return redirect(url_for('profile'))

    flash("An error occurred while updating your Password.", "error")
    return redirect(url_for('profile'))


@app.route('/updateBG', methods=['POST'])
def updateBG():
    username = session.get('username')
    bgImage = request.form['update_img_bg']

    users_ref = db.reference('users')
    users = users_ref.get()

    for user_id, data in users.items():
        if data.get('username') == username:
            users_ref.child(user_id).update({
                'BgImage': bgImage,
            })

            flash("Background Image updated successfully!", "success")
            return redirect(url_for('dashboard'))

    flash("An error occurred while updating the Background Image.", "error")
    return redirect(url_for('dashboard'))

   
@app.route('/dashboard')  # DASHBOARD HTML
def dashboard(): 
    username = session.get('username') 
    
    if not username:
        flash("Please log in to access the dashboard.", "error")
        return redirect(url_for('home'))

    # Fetch all tasks from Firebase
    tasks_ref = db.reference('tasks')
    tasks = tasks_ref.get()

    users_ref = db.reference('users')
    users = users_ref.get()

    achievements_ref = db.reference('achievements')
    achievements = achievements_ref.get()

    all_tasks = []
    notifications = []
    deadline_days = None 
    all_achievements = []

    check_achievement_criteria()

    for achievement_id, achievement_data in achievements.items():
        if achievement_data.get('username') == username:
            if isinstance(achievement_data, dict):  # Check if it's a dictionary
                for achievement_name, achievement_details in achievement_data.items(): 
                    if achievement_name != 'username': 
                        if achievement_details['status'] == 'Completed':
                            all_achievements.append({
                                'name': achievement_name,
                                'logo': achievement_details['logo'],
                            })
            else:
                print(f"Unexpected data type for achievement_data: {type(achievement_data)}")

    for user_id, data in users.items():
        if data.get('username') == username:
                session['background_image'] = data['BgImage']

    if tasks:
        for task_id, task_data in tasks.items():
            if task_data.get('username') == username:
                # Calculate the deadline in days
                deadline_days = (datetime.strptime(task_data['taskDeadline'], '%Y-%m-%d') - datetime.now()).days
                print('TITLE:', task_data['taskName'], 'DUEEE',deadline_days, 'Status', task_data['status'])

                all_tasks.append({
                    'task_id': task_id,
                    'impScale': task_data['importanceScale'],
                    'start': task_data['taskDeadline'],
                    'title': task_data['taskName'],
                    'desc': task_data['taskDesc'],
                    'type': task_data['taskType'],
                    'status': task_data['status'],
                    'priority': task_data.get('priority', 'Not assigned')
                })

                if deadline_days != None:

                    if deadline_days <= 14 and task_data['status'] == 'Pending':
                        if deadline_days < 0:
                            notifications.append(f"{task_data['taskName']} is overdue!")
                        elif deadline_days == 0:
                            notifications.append(f"{task_data['taskName']} is due tommorow!")
                        elif 1 <= deadline_days <= 2:
                            notifications.append(f"{task_data['taskName']} is due in {deadline_days} days.")
                else:
                    notifications.append("No Notification")
    
    # Adjust priorities based on earlier deadlines
    adjust_priorities(all_tasks)

    # Initialize lists for MoSCoW categories
    must_have = []
    should_have = []
    could_have = []
    wont_have = []
    
    for task in all_tasks:
        if task['status'] == 'Pending':
            # Categorize tasks based on the priority stored in the database
            if task['priority'] == "Must Do":
                must_have.append(task)
            elif task['priority'] == "Should Do":
                should_have.append(task)
            elif task['priority'] == "Could Do":
                could_have.append(task)
            elif task['priority'] == "Wait To Do":
                wont_have.append(task)

    #  # Use TaskPrioritizationEnv to adjust existing tasks
    # env = TaskPrioritizationEnv(all_tasks)
    # obs = env.reset()  # Reset the environment to start
    # done = False

    # while not done:
    #     action = env.action_space.sample()  # Sample an action (you can replace this with your own logic)
    #     obs, reward, done, _ = env.step(action)  # Step through the environment

    # # After running the environment, update the priorities of existing tasks
    # for i, task in enumerate(all_tasks):
    #     # Assuming the environment updates the tasks in place or returns updated priorities
    #     task['priority'] = obs[i]['priority'] 


    # Render the dashboard with categorized tasks
    return render_template(
        'dashboard.html', 
        must_have=must_have, 
        should_have=should_have, 
        could_have=could_have, 
        wont_have=wont_have,
        tasks=all_tasks,
        notifications=notifications,
        achievements=all_achievements,
    )

@app.route('/achievements', methods=['GET'])
def achievements():
    try:
    # Fetch all achievements from Firebase
        achievements_ref = db.reference('achievements').get()
        tasks_ref = db.reference('tasks')
        tasks = tasks_ref.get()
        
        # Get the username from the session
        username = session.get('username')

        notifications = []

        # Retrieve notification 
        if tasks:
            for task_id, task_data in tasks.items():
                if task_data.get('username') == username:
                    deadline_days = (datetime.strptime(task_data['taskDeadline'], '%Y-%m-%d') - datetime.now()).days
                    if deadline_days != None:

                        if deadline_days <= 14 and task_data['status'] == 'Pending':
                            if deadline_days < 0:
                                notifications.append(f"{task_data['taskName']} is overdue!")
                            elif deadline_days == 0:
                                notifications.append(f"{task_data['taskName']} is due tommorow!")
                            elif 1 <= deadline_days <= 2:
                                notifications.append(f"{task_data['taskName']} is due in {deadline_days} days.")
                        else:
                            notifications.append("No New Notification")


        
        # Find the achievements corresponding to the logged-in user
        user_achievements = {}
        for key, value in achievements_ref.items():
            if value.get('username') == username:
                user_achievements = value
                break
            
        # check_achievement_criteria()

        return render_template('achievements.html', achievements=user_achievements, notifications=notifications)
    except Exception as e:
        flash(f"An error occurred: {e}", "error")
        return redirect(url_for('dashboard'))

def check_achievement_criteria():
    username = session.get('username')
    print(f"Username from session: {username}") 


    # Fetch achievements and tasks for the user
    achievements_ref = db.reference('achievements')
    achievements = achievements_ref.get()
    all_achievements = []

    tasks_ref = db.reference('tasks')
    tasks = tasks_ref.get()
    all_tasks = []

    if (not tasks or len(tasks) == 0):
        return


    for achievement_id, achievement_data in achievements.items():
        if achievement_data.get('username') == username:
            if isinstance(achievement_data, dict):  # Check if it's a dictionary
                for achievement_name, achievement_details in achievement_data.items(): 
                    if achievement_name != 'username':  # Skip the username entry
                        all_achievements.append({
                            'name': achievement_name, 
                            'status': achievement_details['status'],
                        })
            else:
                print(f"Unexpected data type for achievement_data: {type(achievement_data)}")
    
    
    for task_id, task_data in tasks.items():
        if task_data.get('username') == username:
            if task_data.get('status') == 'Done':
                all_tasks.append({
                    'impScale': task_data['importanceScale'],
                    'start': task_data['taskDeadline'],
                    'title': task_data['taskName'],
                    'type': task_data['taskType'],
                    'status': task_data['status'],
                })
    

    for achievement_id, achievement_data in achievements.items():
        if achievement_data.get('username') == username:
            if isinstance(achievement_data, dict):  # Check if it's a dictionary
                for achievement_name, achievement_details in achievement_data.items():

                    #Complete 1 task
                    if achievement_name == 'newbie':
                        if len(all_tasks) >= 1:
                            if achievement_details['earnedDate'] == 'None':
                                print('TASSKKK:  1', all_tasks)
                                achievements_ref.child(achievement_id).child('newbie').update({
                                    'status': 'Completed',
                                    'earnedDate': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                })  
                    
                    
                    # Check for 'daily_grind' achievement Complete 5 tasks
                    if achievement_name == 'daily_grind':
                        if len(all_tasks) >= 5:
                            if achievement_details['earnedDate'] == 'None':
                                print('TASSKKK 5:  ', all_tasks)
                                achievements_ref.child(achievement_id).child('daily_grind').update({
                                    'status': 'Completed',
                                    'earnedDate': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                })   

                    # Complete 10 Tasks
                    if achievement_name == 'task_master':
                        if len(all_tasks) >= 10:
                            if achievement_details['earnedDate'] == 'None':
                                print('TASSKKK 10:  ', all_tasks)
                                achievements_ref.child(achievement_id).child('task_master').update({
                                    'status': 'Completed',
                                    'earnedDate': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                })    

                    # Check for 'weekend_warrior' achievement (Complete 5 tasks on weekends)
                    if achievement_name == 'weekend_warrior':
                        if achievement_details['earnedDate'] == 'None':
                            weekend_tasks = count_weekend_tasks(all_tasks)
                            if weekend_tasks >= 5:
                                achievements_ref.child(achievement_id).child('weekend_warrior').update({
                                    'status': 'Completed',
                                    'earnedDate': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                })    
                    
                    # Check for 'busy_bee' achievement (Complete 20 tasks in one week)
                    if achievement_name == 'busy_bee':
                        tasks_in_last_week = count_tasks_in_one_week(all_tasks)
                        if tasks_in_last_week >= 20: # 20 na siya
                                achievements_ref.child(achievement_id).child('busy_bee').update({
                                    'status': 'Completed',
                                    'earnedDate': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                })   
                      
                    # Check for 'crammer' achievement (Complete 5 tasks in one day)
                    if achievement_name == 'crammer':
                        tasks_in_one_day = count_tasks_in_one_day(all_tasks)
                        if tasks_in_one_day >= 5:
                                achievements_ref.child(achievement_id).child('crammer').update({
                                    'status': 'Completed',
                                    'earnedDate': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                })
                    
                    # Check for 'streak' achievement (Complete tasks for 5 consecutive days)
                    if achievement_name == 'streak':
                        consecutive_task_days = check_consecutive_task_days(all_tasks)
                        print('STREAK ',consecutive_task_days)
                        if consecutive_task_days >= 5:
                                achievements_ref.child(achievement_id).child('streak').update({
                                    'status': 'Completed',
                                    'earnedDate': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                })
                    
                    # Check for 'marathoner' achievement (Complete 50 tasks in one month)
                    if achievement_name == 'marathoner':
                        tasks_in_last_month = count_tasks_in_last_month(all_tasks)
                        print('TASKS THIS MONTH: ', tasks_in_last_month)
                        if tasks_in_last_month >= 50:
                                achievements_ref.child(achievement_id).child('marathoner').update({
                                    'status': 'Completed',
                                    'earnedDate': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                })
                       


    return "Acquired New Achievement"



# Helper function to check consecutive task completion days
def check_consecutive_task_days(tasks):
    task_dates = sorted([task['start'] for task in tasks])  # Assumes 'date' field in task data
    consecutive_count = 1
    for i in range(1, len(task_dates)):
        if (datetime.strptime(task_dates[i], '%Y-%m-%d') - datetime.strptime(task_dates[i-1], '%Y-%m-%d')).days == 1:
            consecutive_count += 1
        else:
            break
    return consecutive_count

# Helper function to count weekend tasks
def count_weekend_tasks(tasks_ref):
    weekend_task_count = 0
    for task in tasks_ref:
        task_date = task.get('start')  # Assumes 'date' field exists
        print('TASK_DATE FRO CONS: ', task_date)
        task_date_obj = datetime.strptime(task_date, '%Y-%m-%d')
        if task_date_obj.weekday() >= 5:  # Saturday (5) or Sunday (6)
            weekend_task_count += 1
    return weekend_task_count

# Helper function to count tasks in the last week (7 days)
def count_tasks_in_one_week(tasks_ref):
    one_week = datetime.now() + timedelta(days=7)
    task_count = 0
    for task in tasks_ref:
        task_date = task.get('start')  # Assumes 'date' field exists
        task_date_obj = datetime.strptime(task_date, '%Y-%m-%d')
        if task_date_obj <= one_week:
            task_count += 1
    return task_count

# Helper function to count tasks completed on a single day
def count_tasks_in_one_day(tasks_ref):
    task_count_per_day = {}
    for task in tasks_ref:
        task_date = task.get('start')  # Assumes 'date' field exists
        task_date_obj = datetime.strptime(task_date, '%Y-%m-%d')
        task_date_str = task_date_obj.strftime('%Y-%m-%d')
        task_count_per_day[task_date_str] = task_count_per_day.get(task_date_str, 0) + 1
    
    # Return the maximum number of tasks completed on any single day
    return max(task_count_per_day.values(), default=0)

# Helper function to count tasks completed in the last month (30 days)
def count_tasks_in_last_month(tasks_ref):
    one_month = datetime.now() + timedelta(days=30)
    task_count = 0
    for task in tasks_ref:
        task_date = task.get('start')  # Assumes 'date' field exists
        task_date_obj = datetime.strptime(task_date, '%Y-%m-%d')
        if task_date_obj <= one_month:
            task_count += 1
    return task_count


@app.route('/register', methods=['POST'])  # SIGN UP
def register():
    username = request.form['userName']
    email = request.form['email']
    password = request.form['passWord']
    confirm_password = request.form['confPassWord']
    BgImage = 'https://shorturl.at/m7UpZ'

    if password != confirm_password:
        flash("Passwords do not match!", "error")
        return redirect(url_for('signUp')) 
    
    # Initialize user data
    user_data = {
        'username': username,
        'email': email,
        'password': password,
        'BgImage': BgImage
    }

    achievement_status = {
        'newbie': {'name': 'newbie', 'status': 'Ongoing', 'earnedDate': 'None', 'logo': url_for('static', filename='images/newbie.png')},
        'task_master': {'name': 'task_master', 'status': 'Ongoing', 'earnedDate': 'None', 'logo': url_for('static', filename='images/taskmaster.png')},
        'daily_grind': {'name': 'daily_grind', 'status': 'Ongoing', 'earnedDate': 'None', 'logo': url_for('static', filename='images/dailygrind.png')},
        'weekend_warrior': {'name': 'weekend_warrior', 'status': 'Ongoing', 'earnedDate': 'None', 'logo': url_for('static', filename='images/weekendwarrior.png')},
        'busy_bee': {'name': 'busy_bee', 'status': 'Ongoing', 'earnedDate': 'None', 'logo': url_for('static', filename='images/busybee.png')},
        'crammer': {'name': 'crammer', 'status': 'Ongoing', 'earnedDate': 'None', 'logo': url_for('static', filename='images/crammer.png')},
        'streak': {'name': 'streak', 'status': 'Ongoing', 'earnedDate': 'None', 'logo': url_for('static', filename='images/streak.png')},
        'marathoner': {'name': 'marathoner', 'status': 'Ongoing', 'earnedDate': 'None', 'logo': url_for('static', filename='images/marathoner.png')},
        'username': username
    }

    try:
        # Save user data and achievements to Firebase
        db.reference('users').push(user_data)
        db.reference('achievements').push(achievement_status )
        flash("Registration successful! Welcome!", "success")
    except Exception as e:
        flash(f"An error occurred: {e}", "error")
        return redirect(url_for('signUp'))

    return redirect(url_for('home'))


@app.route('/signIn', methods=['POST']) # SIGN-IN Logic
def signIn():
    username = request.form['userName']
    password = request.form['passWord']

    # Retrieve all users from the database
    users_ref = db.reference('users')
    users = users_ref.get()

    if not users:
        flash("Please register an account.", "error")
        return redirect(url_for('home'))

    # Check if the username and password match any user
    for user_id, user_data in users.items():
        if ((user_data['username'] == username or user_data['email'] == username) and user_data['password'] == password):
            # Successful login
            session['username'] = user_data['username']
            session['UserID'] = user_id
            flash("Login successful!")
            return redirect(url_for('dashboard'))  # Redirect to the landing page or dashboard

    # If no match found, flash an error message
    flash("Invalid username or password!", "error")
    return redirect(url_for('home')) 



@app.route('/addtask', methods=['POST']) # ADDS NEW TASK TO THE DATABASE
def addtask():
    username = session.get('username') 
    task_name = request.form['taskName']
    task_desc = request.form['task-desc']
    task_deadline = request.form['taskDeadline']
    importance_scale = request.form['importanceScale']
    task_type = request.form['taskType']

     # Calculate the deadline in days
    deadline_days = (datetime.strptime(task_deadline, '%Y-%m-%d') - datetime.now()).days

    # Use the TaskPrioritizationEngine to determine the priority
    engine = TaskPrioritizationEngine()
    priority = engine.get_priority(int(importance_scale), deadline_days)
    # print('PRIORITY', priority)


    task_data = {
        'taskName': task_name,
        'taskDesc': task_desc,
        'taskDeadline': task_deadline,
        'importanceScale': importance_scale,
        'taskType': task_type,
        'username': username,
        'status': 'Pending',
        'priority' : priority
    }

    try:
        # Store task data in the Firebase Realtime Database
        db.reference('tasks').push(task_data) 
        flash("Task added successfully!")
    except Exception as e:
        flash(f"An error occurred while adding the task: {e}", "error")

    return redirect(url_for('dashboard')) 


@app.route('/updateTask', methods=['POST'])  # UPDATES THE TASKSS
def update_task():
    task_name = request.form['taskNameUpdate']
    task_desc = request.form['task-descUpdate']
    task_deadline = request.form['taskDeadlineUpdate']
    importance_scale = request.form['importanceScaleUpdate']
    task_type = request.form['taskTypeUpdate']
    task_id = request.form['taskIDUpdate'] 
    
    # Calculate the deadline in days
    deadline_days = (datetime.strptime(task_deadline, '%Y-%m-%d') - datetime.now()).days

    # Use the TaskPrioritizationEngine to determine the priority
    engine = TaskPrioritizationEngine()
    priority = engine.get_priority(int(importance_scale), deadline_days)
    # print(task_name, task_deadline, importance_scale, task_type , task_id, priority)

    task_data = {
        'taskName': task_name,
        'taskDesc': task_desc,
        'taskDeadline': task_deadline,
        'importanceScale': importance_scale,
        'taskType': task_type,
        'priority': priority
    }

    try:
        db.reference('tasks').child(task_id).update(task_data)
        flash("Task updated successfully!")

        
        # Fetch all tasks again to adjust priorities
        tasks_ref = db.reference('tasks')
        tasks = tasks_ref.get()
        all_tasks = []

        if tasks:
            for task_id, task_data in tasks.items():
                all_tasks.append({
                    'task_id': task_id,
                    'impScale': task_data['importanceScale'],
                    'start': task_data['taskDeadline'],
                    'title': task_data['taskName'],
                    'desc': task_data['taskDesc'],
                    'type': task_data['taskType'],
                    'status': task_data['status'],
                    'priority': task_data.get('priority', 'Not assigned')
                })

        # # Adjust priorities based on earlier deadlines
        adjust_priorities(all_tasks)

        # Update the priorities in the database if necessary
        for task in all_tasks:
            db.reference('tasks').child(task['task_id']).update({'priority': task['priority']})

    except Exception as e:
        flash(f"An error occurred while updating the task: {e}", "error")

    return redirect(url_for('dashboard')) 


@app.route('/deleteTask/<task_id>', methods=['DELETE']) # DELETESS THE TASKS
def delete_task(task_id):
    
    try:
        db.reference(f'tasks/{task_id}').delete()
        return jsonify({'message': 'Task deleted successfully'}), 200
    except Exception as e:
        print(f"Error deleting task: {e}")
        return jsonify({'error': 'Error deleting task'}), 500 # Return error



@app.route('/markAsDone/<task_id>', methods=['POST']) 
def markAsDone(task_id):
    data = request.get_json()  # Get the JSON data from the request
    new_status = data.get('status')  # Extract the new status

    task_data = {
        'status': new_status
    }

    try:
        db.reference('tasks').child(task_id).update(task_data)
        return jsonify({'message': 'Task status updated to {new_status}'}), 200
    except Exception as e:
        print(f"Error updating task status: {e}")
        return jsonify({'error': 'Error updating task status'}), 500  # Return error
    


if __name__ == '__main__':
    app.run(debug=True)


# Experta AI Engine for Task Prioritization
class TaskPrioritizationEngine(KnowledgeEngine):
    def __init__(self, importance_weight=0.7, deadline_weight=0.5):
        super().__init__()
        self.explanations = []
        self.priority = 'None' 
        self.importance_weight = importance_weight
        self.deadline_weight = deadline_weight

    # @Rule(Fact(importance=P(lambda x: x >= 8), deadline=P(lambda x: x < 3)))
    @Rule(Fact(score=P(lambda x: x >= 6))) 
    def must_have(self):
        self.priority = "Must Do" 
        self.explanations.append("Must have because the importance is high and the deadline is near.")

    # @Rule(Fact(importance=P(lambda x: x > 4), deadline=P(lambda x: x <= 5)))
    @Rule(Fact(score=P(lambda x: 3 <= x < 6)))
    def should_have(self):
        self.priority = "Should Do" 
        self.explanations.append("Should have because the importance is moderate and the deadline is approaching.")

    # @Rule(Fact(importance=P(lambda x: x < 5), deadline=P(lambda x: x > 5)))
    @Rule(Fact(score=P(lambda x: 0.6 <= x < 3)))
    def could_have(self):
        self.priority = "Could Do"
        self.explanations.append("Could have because the importance is low and the deadline is far.")

    # @Rule(Fact(importance=P(lambda x: x < 5), deadline=P(lambda x: x <= 5)))
    @Rule(Fact(score=P(lambda x: x < 0.6)))
    def wont_have(self):
        self.priority = "Wait To Do" 
        self.explanations.append("Won't have because the importance is low, regardless of the deadline.")
    
    def get_priority(self, importance, deadline):
        self.reset()
        if deadline <= 0:
            deadline = 1 
        score = (importance * self.importance_weight) + (1 / deadline) * self.deadline_weight
        self.declare(Fact(importance=importance, deadline=deadline, score=score))
        print("SCORE", score)
        self.run()
        
        return self.priority

def adjust_priorities(all_tasks):
    for i, task in enumerate(all_tasks):
        # Calculate the deadline in days for the current task
        current_deadline_days = (datetime.strptime(task['start'], '%Y-%m-%d') - datetime.now()).days
        
        # Check if the current task is due in 5 days or less
        if current_deadline_days <= 5:
            for j, other_task in enumerate(all_tasks):
                if i != j:  # Don't compare the task with itself
                    # Calculate the deadline in days for the other task
                    other_deadline_days = (datetime.strptime(other_task['start'], '%Y-%m-%d') - datetime.now()).days
                    
                    # Check if the other task has a higher priority and an earlier deadline
                    if other_deadline_days < current_deadline_days and other_task['priority'] < task['priority']:
                        # Decrease the priority of the current task
                        if task['priority'] == "Must Do":
                            task['priority'] = "Should Do"
                        elif task['priority'] == "Should Do":
                            task['priority'] = "Could Do"
                        elif task['priority'] == "Could Do":
                            task['priority'] = "Wait To Do"

# # Gym Environment for Task Prioritization
# class TaskPrioritizationEnv(gym.Env):
#     def __init__(self, tasks):
#         super(TaskPrioritizationEnv, self).__init__()
#         self.tasks = tasks
#         self.current_task = 0
#         self.action_space = spaces.Discrete(4)  # 0: Must have, 1: Should have, 2: Could have, 3: Won't have
#         self.observation_space = spaces.Box(low=0, high=10, shape=(2,), dtype=np.int)  # Importance and Deadline

#         self.engine = TaskPrioritizationEngine()  # Experta engine to check task priority

#     def reset(self):
#         self.current_task = 0
#         return np.array([self.tasks[self.current_task]['importance'], self.tasks[self.current_task]['deadline']])

#     def step(self, action):
#         task = self.tasks[self.current_task]
#         importance, deadline = task['importance'], task['deadline']
        
#         # Get the current priority based on Experta rules
#         current_priority = self.engine.get_priority(importance, deadline)

#         # Adjust the priority based on the action taken
#         if action == 0:  
#             new_priority = 'Must have'
#         elif action == 1:  
#             new_priority = 'Should have'
#         elif action == 2:  
#             new_priority = 'Could have'
#         else: 
#             new_priority = 'Won\'t have'

#         # Update the task's priority based on the new decision
#         task['priority'] = new_priority

#         # Move to the next task
#         self.current_task += 1
#         done = self.current_task >= len(self.tasks)

#         # Return the new observation, reward, and done status
#         return self.reset() if not done else (None, 0, done, {})
