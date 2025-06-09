import os
import pickle
import numpy as np
import pandas as pd
from flask import Flask, request, jsonify, render_template, redirect, flash,session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from PIL import Image
from tensorflow.keras.preprocessing.image import img_to_array # type: ignore
from tensorflow.keras.models import load_model # type: ignore
from datetime import datetime
from io import BytesIO
from bcrypt import hashpw, gensalt,checkpw
from base64 import b64encode
# Initialize Flask app
app = Flask(__name__)
app.secret_key = "kDvBx*eRd9<Y$^Ut'ns?)u"


# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:Akushi@localhost:3306/predictions'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads/'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database
db = SQLAlchemy(app)

# Load the trained model and label encoder
model = load_model('model\model.h5')  # Replace with your trained model file path
label_encoder = pickle.load(open('model\model.pkl', 'rb'))  # Label encoder file

# Load nutrition data
data = pd.read_csv("dataset\indian_dishes_nutrients.csv")

# Allowed extensions for uploaded files
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    """Check if the file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database Models
class Prediction(db.Model):
    __tablename__ = 'predictions'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Linking donor details
    food_name = db.Column(db.String(100), nullable=False)
    predicted_food = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    date = db.Column(db.String(100), nullable=False)
    nutrients = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    image = db.Column(db.LargeBinary)  # For storing image data
    age_group = db.Column(db.String(20), nullable=False)  # New column for age group
    # Foreign Key: Linking to User
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    fullname = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # Donor or Receiver
    mobile = db.Column(db.String(15), nullable=False)
    id_image = db.Column(db.LargeBinary)  # Store image as BLOB
    address = db.Column(db.Text, nullable=False)
    # Relationship: One user can have multiple donations
    predictions = db.relationship('Prediction', backref='user')

class Orders(db.Model):  # New table for orders
    id = db.Column(db.Integer, primary_key=True)
    prediction_id = db.Column(db.Integer, db.ForeignKey('predictions.id'), nullable=False)
    food_name = db.Column(db.String(100), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_name = db.Column(db.String(100), nullable=False)
    receiver_phone = db.Column(db.String(20), nullable=False)
    receiver_location = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default="Confirmed") 

    predictions = db.relationship("Prediction", backref="orders")
    receiver = db.relationship("User", backref="orders")
  
# Routes
@app.route('/')
def home():
    """Render the homepage."""
    return render_template('Home(MAIN).html')


@app.route('/donor')
def donor():
    user_id = session.get('user_id')
    user_data = {}
    orders = []
    donations = []

    if user_id:
        user = User.query.get(user_id)
        if user:
            user_data = {
                'id': user.id,
                'name': user.fullname,
                'email': user.email,
                'phone': user.mobile,
                'address': user.address,
            }

            # --------------------
            # Fetch Orders for This Donor's Predictions
            # --------------------
            orders_query = (
                db.session.query(Orders)
                .join(Prediction, Orders.prediction_id == Prediction.id)
                .filter(Prediction.user_id == user.id)
                .all()
            )

            for order in orders_query:
                orders.append({
                    'id': order.id,
                    'receiver_name': order.receiver_name,
                    'food_name': order.food_name,
                    'quantity': order.predictions.quantity,
                    'contact': order.receiver_phone,
                    'address': order.receiver_location,
                    'date': order.predictions.date
                })

            # --------------------
            # Fetch All Donations Made by This Donor
            # --------------------
            donations_query = Prediction.query.filter_by(user_id=user.id).all()
            for d in donations_query:
                donations.append({
                    'id': d.id,
                    'food_name': d.food_name,
                    'predicted_food': d.predicted_food,
                    'quantity': d.quantity,
                    'age_group': d.age_group,
                    'date': d.date,
                })
    else:
        user_data = {
            'id': 0,
            'name': 'Guest',
            'email': '',
            'phone': '',
            'address': ''
        }

    return render_template('donorpage3.html', user=user_data, orders=orders, donations=donations)



    

@app.route('/predict', methods=['POST'])
def predict():
    """Predict food category and return nutrient details."""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    name = request.form.get('name')
    quantity = float(request.form.get('quantity'))
    date = request.form.get('date')
    age_group = request.form.get('age-group')

    # Retrieve user_id from session or form
    user_id = session.get('user_id') or request.form.get('user_id')

    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    # Prepare user_data dictionary for template
    user_data = {}
    if user_id:
        user = User.query.get(user_id)
        if user:
            user_data = {
                'id': user.id,
                'name': user.fullname,
                'email': user.email,
                'phone': user.mobile,
                'address': user.address,
            }
    else:
        user_data = {
            'id': 0,
            'name': 'Guest',
            'email': '',
            'phone': '',
            'address': ''
        }

    if file and allowed_file(file.filename):
        try:
            # Process image
            image = Image.open(file).convert('RGB')
            image = image.resize((128, 128))
            image_array = img_to_array(image) / 255.0
            image_array = np.expand_dims(image_array, axis=0)

            # Convert image to binary data
            img_byte_arr = BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()

            # Predict food category
            prediction_index = np.argmax(model.predict(image_array))
            predicted_class = label_encoder.inverse_transform([prediction_index])[0]

            # Retrieve nutrients
            if predicted_class in data['Food'].values:
                nutrients = data[data['Food'] == predicted_class].iloc[:, 1:].to_dict('records')[0]
                nutrient_info = "\n".join([f"{key}: {value}" for key, value in nutrients.items()])
            else:
                nutrient_info = "Nutritional information not available."

            # Save prediction to database with image as binary data
            prediction_entry = Prediction(
                user_id=user_id,
                food_name=name,
                predicted_food=predicted_class,
                quantity=quantity,
                date=date,
                age_group=age_group,
                nutrients=nutrient_info,
                image=img_byte_arr  # Save image as binary data
            )
            db.session.add(prediction_entry)
            db.session.commit()

            # Render result with user data included
            return render_template(
                "donorpage3.html",
                prediction_text=f" {predicted_class}\n",
                nutrient_info=f"Nutritional Info:\n{nutrient_info}\n"
                              f"Food Name: {name}\n"
                              f"Quantity: {quantity} kg\n"
                              f"Date: {date}\n"
                              f"Age Group: {age_group}",
                user=user_data  # Pass user data here!
            )
        except Exception as e:
            return jsonify({"error": f"Error processing the image: {str(e)}"}), 500

    return jsonify({"error": "Invalid file type. Please upload a valid image."}), 400


@app.route('/receiver', methods=['GET', 'POST'])
def receiver():
    """Handles displaying predictions and saving receiver orders."""

    user_id = session.get("user_id")
    if not user_id:
        return redirect('/login')  # or handle unauthorized access

    if request.method == 'POST':
        data = request.get_json()
        cart_items = data.get("cart", [])

        user = User.query.get(user_id)
        if not user:
            return jsonify({'status': 'error', 'message': 'User not found'}), 404

        for item in cart_items:
            prediction_id = item.get("id")
            if not prediction_id:
                continue  # skip if ID is missing

            prediction = Prediction.query.get(prediction_id)
            if not prediction:
                continue

            new_order = Orders(
                prediction_id=prediction_id,
                receiver_id=user.id,
                food_name=prediction.food_name,
                receiver_name=user.fullname,
                receiver_phone=user.mobile,
                receiver_location=user.address,
                status="Confirmed"
            )
            db.session.add(new_order)

        db.session.commit()
        return jsonify({'status': 'success'})

    # --- GET logic: show predictions and profile ---
    predictions = Prediction.query.all()
    prediction_list = []

    for prediction in predictions:
        image_data = b64encode(prediction.image).decode('utf-8') if prediction.image else None

        order = Orders.query.filter_by(prediction_id=prediction.id).first()
        status = order.status if order else "Not Ordered"

        prediction_data = {
            'id': prediction.id,
            'food_name': prediction.food_name,
            'predicted_food': prediction.predicted_food,
            'quantity': prediction.quantity,
            'date': prediction.date,
            'nutrients': prediction.nutrients,
            'age_group': prediction.age_group,
            'donor_name': prediction.user.fullname if prediction.user else 'Unknown',
            'number': prediction.user.mobile if prediction.user else 'N/A',
            'donor_address': prediction.user.address if prediction.user else 'N/A',
            'status': status,
            'image': image_data,
            'receiver_name': order.receiver_name if order else None
        }
        prediction_list.append(prediction_data)

    # Fetch only current user's orders
    orders = Orders.query.filter_by(receiver_id=user_id).all()
    order_list = []
    for order in orders:
        order_list.append({
            'food_name': order.food_name,
            'status': order.status,
            'receiver_name': order.receiver_name,
            'receiver_phone': order.receiver_phone,
            'receiver_location': order.receiver_location
        })

    # User profile details (replace with actual implementation)
    user = User.query.get(user_id)
    user_data = {
        'name': user.fullname,
        'email': user.email,
        'role': user.role,
        'mobile': user.mobile,
        'address': user.address
    }

    return render_template('receiver.html',
                           predictions=prediction_list,
                           user=user_data,
                           orders=order_list)




@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"].encode("utf-8")  # ✅ Convert password to bytes for bcrypt
        
        # Fetch user from the database
        user = User.query.filter_by(email=email).first()  # ✅ Use user, not User

        # Check if user exists and verify password
        if user and checkpw(password, user.password.encode("utf-8")):  # ✅ Hash comparison
            session["user_id"] = user.id  # ✅ Store user session
            
            # Redirect based on user role
            if user.role == "donor":
                return redirect("/donor")
            elif user.role == "receiver":
                return redirect("/receiver")

        # If authentication fails, show an error
        return render_template("login.html", error="Invalid email or password.")

    # Render login page for GET requests
    return render_template("login.html")

@app.route("/about")
def about():
    return render_template("about.html")

    
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Handle user signup."""
    if request.method == 'POST':
        try:
            # Retrieve form data (Fixing request.form.get syntax)
            fullname = request.form.get('fullname')
            email = request.form.get('email')
            password = request.form.get('password')
            role = request.form.get('options')
            mobile = request.form.get('mobile')
            address = request.form.get('address')
            file = request.files['image']

            # Validate required fields
            if not (fullname and email and password and role and mobile and address and file):
                flash("All fields are required, including an ID image.", "danger")
                return redirect('/signup')

            # Validate image file
            if not allowed_file(file.filename):
                flash("Invalid image file. Allowed formats: png, jpg, jpeg.", "danger")
                return redirect('/signup')

            # Convert image to binary for storage in the database
            img_binary = file.read()  # Read binary data

            # Hash the password before saving
            hashed_password = hashpw(password.encode('utf-8'), gensalt())

            # Insert user into the database
            new_user = User(
                fullname=fullname,
                email=email,
                password=hashed_password.decode('utf-8'),  # Store hashed password
                role=role,
                mobile=mobile,
                id_image=img_binary,  # Store image binary data
                address=address
            )
            db.session.add(new_user)
            db.session.commit()

            flash("Account created successfully!", "success")
            return redirect('/login')  # Redirect to the login page

        except Exception as e:
            db.session.rollback()  # Rollback in case of an error
            flash(f"Error: {str(e)}", "danger")
            return redirect('/signup')

    return render_template('Signup.html')  # Render the signup form

@app.route('/claim_order', methods=['POST'])
def claim_order():
    data = request.json
    prediction_id = data.get("prediction_id")
    receiver_id = data.get("receiver_id")
    receiver_name = data.get("receiver_name")
    receiver_phone = data.get("receiver_phone")
    receiver_location = data.get("receiver_location")

    if not all([prediction_id, receiver_id, receiver_name, receiver_phone, receiver_location]):
        return jsonify({"error": "Missing required fields"}), 400

    order = Orders(
        prediction_id=prediction_id,
        receiver_id=receiver_id,
        receiver_name=receiver_name,
        receiver_phone=receiver_phone,
        receiver_location=receiver_location,
        status="Confirmed"
    )

    db.session.add(order)
    db.session.commit()
    return jsonify({"message": "Order placed successfully"}), 201





# Create tables on app start
with app.app_context():
    db.create_all()

# Run the app
if __name__ == "__main__":
    app.run(debug=True)


