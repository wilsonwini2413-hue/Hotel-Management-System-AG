from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Database Configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'hms.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev-secret-key-replace-in-prod'

db = SQLAlchemy(app)

# Models
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Guest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    id_type = db.Column(db.String(50)) # Aadhaar, Passport, etc.
    id_number = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    aadhar_number = db.Column(db.String(20))
    mobile_number = db.Column(db.String(20))

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(10), unique=True, nullable=False)
    room_type = db.Column(db.String(50), nullable=False) # Single, Double, Suite
    price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Available') # Available, Occupied, Maintenance, Cleaning

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    guest_id = db.Column(db.Integer, db.ForeignKey('guest.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    check_in = db.Column(db.DateTime, default=datetime.utcnow)
    check_out = db.Column(db.DateTime)
    total_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='Active') # Active, CheckedOut, Cancelled

class RestaurantBill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'), nullable=False)
    item_description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class LaundryBill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'), nullable=False)
    service_type = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class GameBill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'), nullable=False)
    game_type = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# API Routes
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    admin = Admin.query.filter_by(username=data.get('username')).first()
    if admin and admin.password == data.get('password'):
        return jsonify({"message": "Login successful", "user": admin.username}), 200
    return jsonify({"message": "Invalid credentials"}), 401

@app.route('/api/rooms', methods=['GET'])
def get_rooms():
    rooms = Room.query.all()
    return jsonify([{
        "id": r.id, 
        "room_number": r.room_number, 
        "room_type": r.room_type, 
        "price": r.price, 
        "status": r.status
    } for r in rooms])
@app.route('/api/guests', methods=['GET'])
def get_guests():
    results = db.session.query(Guest, Booking, Room).join(
        Booking, Guest.id == Booking.guest_id
    ).join(
        Room, Booking.room_id == Room.id
    ).all()
    
    guests_list = []
    for guest, booking, room in results:
        guests_list.append({
            "id": guest.id,
            "booking_id": booking.id,
            "name": guest.name,
            "mobile": guest.mobile_number,
            "aadhar": guest.aadhar_number,
            "room_number": room.room_number,
            "room_type": room.room_type,
            "check_in": booking.check_in.strftime('%Y-%m-%d %H:%M'),
            "status": booking.status
        })
    return jsonify(guests_list)

@app.route('/api/bookings/<int:booking_id>/bills', methods=['POST'])
def add_bill(booking_id):
    data = request.json
    service_type = data.get('type') # restaurant, laundry, games
    description = data.get('description')
    amount = float(data.get('amount'))

    if service_type == 'restaurant':
        bill = RestaurantBill(booking_id=booking_id, item_description=description, amount=amount)
    elif service_type == 'laundry':
        bill = LaundryBill(booking_id=booking_id, service_type=description, amount=amount)
    elif service_type == 'games':
        bill = GameBill(booking_id=booking_id, game_type=description, amount=amount)
    else:
        return jsonify({"message": "Invalid service type"}), 400

    db.session.add(bill)
    db.session.commit()
    return jsonify({"message": f"{service_type.capitalize()} bill added successfully"}), 201

@app.route('/api/bookings/<int:booking_id>/invoice', methods=['GET'])
def get_invoice(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    guest = Guest.query.get(booking.guest_id)
    room = Room.query.get(booking.room_id)
    
    # Use current time if not checked out yet for preview
    check_out_time = booking.check_out or datetime.utcnow()
    duration = check_out_time - booking.check_in
    nights = max(1, duration.days + (1 if duration.seconds > 0 else 0))
    
    room_charges = nights * room.price
    
    res_bills = RestaurantBill.query.filter_by(booking_id=booking_id).all()
    lau_bills = LaundryBill.query.filter_by(booking_id=booking_id).all()
    gam_bills = GameBill.query.filter_by(booking_id=booking_id).all()
    
    items = [{"description": f"Room {room.room_number} Stay ({nights} nights)", "amount": room_charges}]
    total = room_charges
    
    for b in res_bills:
        items.append({"description": f"Restaurant: {b.item_description}", "amount": b.amount})
        total += b.amount
    for b in lau_bills:
        items.append({"description": f"Laundry: {b.service_type}", "amount": b.amount})
        total += b.amount
    for b in gam_bills:
        items.append({"description": f"Games: {b.game_type}", "amount": b.amount})
        total += b.amount
        
    return jsonify({
        "guest_name": guest.name,
        "room_number": room.room_number,
        "check_in": booking.check_in.strftime('%Y-%m-%d %H:%M'),
        "check_out": check_out_time.strftime('%Y-%m-%d %H:%M'),
        "items": items,
        "nights": nights,
        "total": total
    })

@app.route('/api/billing/history', methods=['GET'])
def get_billing_history():
    # Only show CheckedOut bookings
    results = db.session.query(Guest, Booking, Room).join(
        Booking, Guest.id == Booking.guest_id
    ).join(
        Room, Booking.room_id == Room.id
    ).filter(Booking.status == 'CheckedOut').order_by(Booking.check_out.desc()).all()
    
    history = []
    for guest, booking, room in results:
        # Calculate total for history overview
        duration = booking.check_out - booking.check_in
        nights = max(1, duration.days + (1 if duration.seconds > 0 else 0))
        room_charges = nights * room.price
        
        service_total = sum(b.amount for b in RestaurantBill.query.filter_by(booking_id=booking.id).all())
        service_total += sum(b.amount for b in LaundryBill.query.filter_by(booking_id=booking.id).all())
        service_total += sum(b.amount for b in GameBill.query.filter_by(booking_id=booking.id).all())
        
        history.append({
            "booking_id": booking.id,
            "guest_name": guest.name,
            "room_number": room.room_number,
            "check_out": booking.check_out.strftime('%Y-%m-%d %H:%M'),
            "nights": nights,
            "total_amount": room_charges + service_total
        })
        
    return jsonify(history)

@app.route('/api/bookings/<int:booking_id>/checkout', methods=['POST'])
def checkout_booking(booking_id):
    data = request.json or {}
    booking = Booking.query.get_or_404(booking_id)
    booking.status = 'CheckedOut'
    
    if data.get('check_out'):
        booking.check_out = datetime.strptime(data['check_out'], '%Y-%m-%dT%H:%M')
    else:
        booking.check_out = datetime.utcnow()
    
    room = Room.query.get(booking.room_id)
    room.status = 'Cleaning'
    
    db.session.commit()
    return jsonify({"message": f"Guest checked out, Room {room.room_number} is now being cleaned."}), 200

@app.route('/api/bookings', methods=['POST'])
def create_booking():
    data = request.json
    new_guest = Guest(
        name=data['guest_name'], 
        mobile_number=data.get('mobile_number'),
        address=data.get('address'),
        aadhar_number=data.get('aadhar_number')
    )
    db.session.add(new_guest)
    db.session.flush()
    
    new_booking = Booking(
        guest_id=new_guest.id,
        room_id=int(data['room_id']),
        check_in=datetime.strptime(data['check_in'], '%Y-%m-%dT%H:%M') if data.get('check_in') else datetime.utcnow(),
        check_out=datetime.strptime(data['check_out'], '%Y-%m-%dT%H:%M') if data.get('check_out') else None
    )
    db.session.add(new_booking)
    
    room = Room.query.get(int(data['room_id']))
    room.status = 'Occupied'
    
    db.session.commit()
    return jsonify({"message": "Booking created", "booking_id": new_booking.id}), 201

@app.route('/api/rooms/<int:room_id>/status', methods=['PUT'])
def update_room_status(room_id):
    data = request.json
    room = Room.query.get_or_404(room_id)
    if 'status' in data:
        room.status = data['status']
        db.session.commit()
        return jsonify({"message": f"Room {room.room_number} status updated to {room.status}"}), 200
    return jsonify({"message": "Status not provided"}), 400

# Database Initialization
def init_db():
    with app.app_context():
        db.create_all()
        # Create default admin if not exists
        if not Admin.query.filter_by(username='admin').first():
            default_admin = Admin(username='admin', password='password123')
            db.session.add(default_admin)
            
            # Seed 20 random rooms
            if not Room.query.first():
                import random
                rooms = []
                room_types = [('Standard', 1500), ('Deluxe', 2500), ('Suite', 5000)]
                for i in range(1, 21):
                    room_type, price = random.choice(room_types)
                    # Generate random room number like 101, 204, etc.
                    floor = random.randint(1, 5)
                    r_num = random.randint(1, 20)
                    room_number = f"{floor}{r_num:02d}"
                    
                    rooms.append(Room(
                        room_number=room_number,
                        room_type=room_type,
                        price=price,
                        status=random.choice(['Available', 'Available', 'Available', 'Occupied', 'Occupied', 'Maintenance', 'Cleaning'])
                    ))
                
                db.session.add_all(rooms)
            
            db.session.commit()
            print("Default admin and rooms created!")

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=8080)
