from flask import (
    Flask, render_template, request, redirect,
    session, url_for, send_file
)
import os
from dotenv import load_dotenv

load_dotenv()
from datetime import date, datetime
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import date
from decimal import Decimal, ROUND_HALF_UP,InvalidOperation
import mysql.connector
import os

app = Flask(__name__)

# Keep your secret key private.
# Set FLASK_SECRET_KEY in your environment before deployment.
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "local-development-key-change-before-deployment"
)


# Database connection
def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )



# Login protection
def login_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return route_function(*args, **kwargs)
    return wrapper

# ==============================
# ROLE PERMISSION DECORATOR
# ==============================

def role_required(*allowed_roles):

    def decorator(f):

        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):

            if session.get("role") not in allowed_roles:
                return (
                    "Access denied. You do not have permission "
                    "to access this page.",
                    403
                )

            return f(*args, **kwargs)

        return decorated_function

    return decorator

# ==============================
# PUBLIC WEBSITE
# ==============================
@app.route("/")
def home():
    return render_template("home.html")

# ==============================
# LOGIN
# ==============================

@app.route("/login", methods=["GET", "POST"])
def login():

    # Already logged in
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        db = get_db()
        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT * FROM admin_users WHERE username = %s",
                (username,)
            )

            admin = cursor.fetchone()

        finally:
            cursor.close()
            db.close()

        if (
            admin
            and admin["is_active"]
            and check_password_hash(admin["password_hash"], password)
        ):
            session.clear()

            session["user_id"] = admin["user_id"]
            session["username"] = admin["username"]
            session["role"] = admin["role"]

            return redirect(url_for("dashboard"))

        return render_template(
            "login.html",
            error="Invalid username or password"
        )

    return render_template("login.html")


# ==============================
# LOGOUT
# ==============================

@app.route("/logout")
def logout():

    # Clear all login session data
    session.clear()

    # Return to login page
    return redirect(url_for("home"))


# ==============================
# MANAGEMENT DASHBOARD
# ==============================

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


# ==============================
# CUSTOMER MANAGEMENT
# ==============================

@app.route("/customers", methods=["GET", "POST"])
@login_required
def customers():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":

        name = request.form["customer_name"]
        phone = request.form["phone"]
        address = request.form["address"]

        cursor.execute("""
            INSERT INTO customers
            (customer_name, phone, address)
            VALUES (%s, %s, %s)
        """, (name, phone, address))

        db.commit()
        cursor.close()
        db.close()

        return redirect("/customers")

    cursor.execute("SELECT * FROM customers")
    customer_list = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "customers.html",
        customers=customer_list
    )


@app.route("/edit_customer/<int:id>", methods=["GET", "POST"])
@login_required
def edit_customer(id):

    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":

        name = request.form["customer_name"]
        phone = request.form["phone"]
        address = request.form["address"]

        cursor.execute("""
            UPDATE customers
            SET customer_name=%s,
                phone=%s,
                address=%s
            WHERE customer_id=%s
        """, (name, phone, address, id))

        db.commit()
        cursor.close()
        db.close()

        return redirect("/customers")

    cursor.execute(
        "SELECT * FROM customers WHERE customer_id=%s",
        (id,)
    )

    customer = cursor.fetchone()

    cursor.close()
    db.close()

    if customer is None:
        return "Customer not found", 404

    return render_template(
        "edit_customer.html",
        customer=customer
    )


@app.route("/delete_customer/<int:id>", methods=["POST"])
@login_required
def delete_customer(id):

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM sales_orders
        WHERE customer_id=%s
    """, (id,))

    result = cursor.fetchone()

    if result["total"] > 0:
        cursor.close()
        db.close()

        return """
        <script>
            alert("This customer has existing sales orders and cannot be deleted.");
            window.location.href="/customers";
        </script>
        """

    cursor.execute(
        "DELETE FROM customers WHERE customer_id=%s",
        (id,)
    )

    db.commit()
    cursor.close()
    db.close()

    return """
    <script>
        alert("Customer deleted successfully!");
        window.location.href="/customers";
    </script>
    """



# ==============================
# PRODUCT MANAGEMENT
# ==============================

@app.route("/products", methods=["GET", "POST"])
@login_required
def products():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Only Admin and Manager can add products
    if request.method == "POST":

        if session.get("role") not in ["Admin", "Manager"]:
            cursor.close()
            db.close()
            return "Access denied. You cannot add products.", 403

        name = request.form["product_name"]
        price = request.form["price"]
        quantity = request.form["quantity"]
        gst_rate = request.form["gst_rate"]

        cursor.execute("""
            INSERT INTO products
            (product_name, price, quantity, gst_rate)
            VALUES (%s, %s, %s, %s)
        """, (name, price, quantity, gst_rate))

        db.commit()
        cursor.close()
        db.close()

        return redirect("/products")

    # All logged-in users can view products
    cursor.execute("SELECT * FROM products ORDER BY product_id ASC")

    product_list = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "products.html",
        products=product_list,
        role=session.get("role")
    )


@app.route("/edit_product/<int:id>", methods=["GET", "POST"])
@login_required
def edit_product(id):

    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":

        name = request.form["product_name"]
        price = request.form["price"]
        quantity = request.form["quantity"]
        gst_rate = request.form["gst_rate"]

        cursor.execute("""
            UPDATE products
            SET product_name=%s,
                price=%s,
                quantity=%s,
                gst_rate=%s
            WHERE product_id=%s
        """, (name, price, quantity, gst_rate, id))

        db.commit()
        cursor.close()
        db.close()

        return redirect("/products")

    cursor.execute(
        "SELECT * FROM products WHERE product_id=%s",
        (id,)
    )

    product = cursor.fetchone()

    cursor.close()
    db.close()

    if product is None:
        return "Product not found", 404

    return render_template(
        "edit_product.html",
        product=product
    )


@app.route("/delete_product/<int:id>", methods=["POST"])
@login_required
def delete_product(id):

    db = get_db()
    cursor = db.cursor()

    tables = [
        "sales_orders",
        "production",
        "production_costs"
    ]

    for table in tables:

        cursor.execute(
            f"SELECT COUNT(*) FROM {table} WHERE product_id=%s",
            (id,)
        )

        if cursor.fetchone()[0] > 0:

            cursor.close()
            db.close()

            return """
            <script>
                alert("This product is already used in records and cannot be deleted.");
                window.location.href="/products";
            </script>
            """

    cursor.execute(
        "DELETE FROM products WHERE product_id=%s",
        (id,)
    )

    db.commit()
    cursor.close()
    db.close()

    return """
    <script>
        alert("Product deleted successfully!");
        window.location.href="/products";
    </script>
    """


# ==============================
# SALES ORDER MANAGEMENT
# ==============================

@app.route("/sales", methods=["GET", "POST"])
@login_required
def sales():

    db = get_db()
    cursor = db.cursor(dictionary=True)
    message = ""

    if request.method == "POST":
        try:
            customer_id = int(request.form["customer_id"])
            product_id = int(request.form["product_id"])
            quantity = int(request.form["quantity"])

            if quantity <= 0:
                raise ValueError("Quantity must be greater than zero.")

            cursor.execute("""
                SELECT price, quantity
                FROM products
                WHERE product_id = %s
            """, (product_id,))
            product = cursor.fetchone()

            if product is None:
                raise ValueError("Product not found.")

            if quantity > product["quantity"]:
                raise ValueError("Not enough stock available.")

            cursor.execute("""
                SELECT customer_id
                FROM customers
                WHERE customer_id = %s
            """, (customer_id,))
            if cursor.fetchone() is None:
                raise ValueError("Customer not found.")

            total = product["price"] * quantity

            cursor.execute("""
                INSERT INTO sales_orders
                (customer_id, product_id, order_date,
                 quantity, total_amount, order_status)
                VALUES (%s, %s, %s, %s, %s, 'Pending')
            """, (
                customer_id,
                product_id,
                date.today(),
                quantity,
                total
            ))

            db.commit()
            message = "Sales order created and sent for approval. Stock will update after approval."

        except (ValueError, InvalidOperation) as e:
            db.rollback()
            message = str(e)

        except Exception as e:
            db.rollback()
            print("SALES ERROR:", repr(e))
            message = "Could not create sales order. Please check the details."

    cursor.execute("SELECT * FROM customers ORDER BY customer_name")
    customer_list = cursor.fetchall()

    cursor.execute("SELECT * FROM products ORDER BY product_name")
    product_list = cursor.fetchall()

    cursor.execute("""
        SELECT s.*, c.customer_name, p.product_name
        FROM sales_orders s
        JOIN customers c ON s.customer_id = c.customer_id
        JOIN products p ON s.product_id = p.product_id
        ORDER BY s.order_id ASC
    """)
    order_list = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "sales.html",
        customers=customer_list,
        products=product_list,
        orders=order_list,
        message=message
    )



# ==============================
# GST BILLING
# ==============================


@app.route("/billing")
@login_required
def billing():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            s.order_id,
            s.order_date,
            s.quantity,
            s.total_amount,
            s.order_status,
            c.customer_name,
            c.phone,
            c.address,
            p.product_name,
            p.price,
            p.gst_rate
        FROM sales_orders s
        JOIN customers c ON s.customer_id = c.customer_id
        JOIN products p ON s.product_id = p.product_id
        ORDER BY s.order_id ASC
    """)

    orders = cursor.fetchall()

    for order in orders:

        subtotal = Decimal(str(order["total_amount"]))
        gst_rate = Decimal(str(order["gst_rate"]))

        gst_amount = (
            subtotal * gst_rate / Decimal("100")
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

        cgst = (
            gst_amount / Decimal("2")
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

        sgst = gst_amount - cgst
        igst = Decimal("0.00")

        grand_total = subtotal + gst_amount

        order["subtotal"] = subtotal
        order["gst_rate"] = gst_rate
        order["gst_amount"] = gst_amount
        order["cgst"] = cgst
        order["sgst"] = sgst
        order["igst"] = igst
        order["grand_total"] = grand_total

    cursor.close()
    db.close()

    return render_template(
        "billing.html",
        orders=orders
    )


# ==============================
# PRODUCTION MANAGEMENT
# ==============================

@app.route("/production", methods=["GET", "POST"])
@login_required
def production():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    message = request.args.get("message", "")

    if request.method == "POST":

        try:
            product_id = int(request.form["product_id"])
            planned_quantity = int(request.form["planned_quantity"])
            actual_quantity = int(request.form["actual_quantity"])
            wastage_quantity = int(request.form["wastage_quantity"])
            variance_note = request.form.get("variance_note", "").strip()

            if planned_quantity <= 0:
                raise ValueError("Planned quantity must be greater than zero.")

            if actual_quantity <= 0:
                raise ValueError("Actual quantity must be greater than zero.")

            if wastage_quantity < 0:
                raise ValueError("Wastage cannot be negative.")

            # Check product exists
            cursor.execute("""
                SELECT product_id
                FROM products
                WHERE product_id = %s
            """, (product_id,))

            product = cursor.fetchone()

            if product is None:
                raise ValueError("Product not found.")

            # Save production record
            cursor.execute("""
                INSERT INTO production
                (product_id, production_date, quantity)
                VALUES (%s, %s, %s)
            """, (
                product_id,
                date.today(),
                actual_quantity
            ))

            production_id = cursor.lastrowid

            
            # Increase finished product stock
            cursor.execute("""
                UPDATE products
                SET quantity = quantity + %s
                WHERE product_id = %s
        """, (actual_quantity, product_id))

            # Record finished product stock movement
            cursor.execute("""
                INSERT INTO stock_movements
                (product_id, movement_type, quantity, reference_note)
                VALUES (%s, %s, %s, %s)
            """, (
            product_id,
            "PRODUCTION_IN",
            actual_quantity,
            f"Production ID: {production_id}"
        ))

            # Save production variance
            cursor.execute("""
                INSERT INTO production_variances
                (
                    production_id,
                    planned_quantity,
                    actual_quantity,
                    wastage_quantity,
                    variance_note
                )
                VALUES (%s, %s, %s, %s, %s)
            """, (
                production_id,
                planned_quantity,
                actual_quantity,
                wastage_quantity,
                variance_note
            ))

            # Save audit record
            cursor.execute("""
                INSERT INTO audit_trail
                (user_id, action, details)
                VALUES (%s, %s, %s)
            """, (
                session["user_id"],
                "Production Recorded",
                f"Production ID {production_id}: "
                f"Planned {planned_quantity}, "
                f"Actual {actual_quantity}, "
                f"Wastage {wastage_quantity}"
            ))

            db.commit()

            return redirect(url_for(
                "production",
                message="Production and variance saved successfully!"
            ))

        except Exception as e:
            db.rollback()
            print("PRODUCTION ERROR:", repr(e))
            message = f"Could not save production: {e}"

    # Get products
    cursor.execute("""
        SELECT *
        FROM products
        ORDER BY product_name
    """)

    product_list = cursor.fetchall()

    # Get production history and variance details
    cursor.execute("""
        SELECT
            p.production_id,
            p.production_date,
            p.quantity,
            pr.product_name,
            v.planned_quantity,
            v.actual_quantity,
            v.wastage_quantity,
            v.variance_note
        FROM production p
        JOIN products pr
            ON p.product_id = pr.product_id
        LEFT JOIN production_variances v
            ON p.production_id = v.production_id
        ORDER BY p.production_id DESC
    """)

    production_list = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "production.html",
        products=product_list,
        records=production_list,
        message=message
    )





# ==============================
# INVENTORY MANAGEMENT
# ==============================

@app.route("/inventory", methods=["GET", "POST"])
@login_required
def inventory():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    message = request.args.get("message", "")

    if request.method == "POST":

        # Only Admin and Manager can add raw materials
        if session.get("role") not in ["Admin", "Manager"]:
            cursor.close()
            db.close()
            return "Access denied. You cannot modify inventory.", 403

        try:
            name = request.form["material_name"].strip()
            quantity = Decimal(request.form["quantity"])
            unit = request.form["unit"]

            if not name:
                raise ValueError("Material name is required.")

            if quantity <= 0:
                raise ValueError("Quantity must be greater than zero.")

            if unit not in ["Kg", "Gram", "Litre", "Packet"]:
                raise ValueError("Please select a valid unit.")

            # Add raw material
            cursor.execute("""
                INSERT INTO raw_materials
                (material_name, quantity, unit)
                VALUES (%s, %s, %s)
            """, (name, quantity, unit))

            material_id = cursor.lastrowid

            # Record stock movement
            cursor.execute("""
                INSERT INTO stock_movements
                (material_id, movement_type, quantity, reference_note)
                VALUES (%s, %s, %s, %s)
            """, (
                material_id,
                "MATERIAL_ADDED",
                quantity,
                "New raw material added to inventory"
            ))

            # Record audit trail
            cursor.execute("""
                INSERT INTO audit_trail
                (user_id, action, details)
                VALUES (%s, %s, %s)
            """, (
                session["user_id"],
                "Raw Material Added",
                f"{name}: {quantity} {unit}"
            ))

            db.commit()

            return redirect(url_for(
                "inventory",
                message="Raw material added successfully!"
            ))

        except (ValueError, InvalidOperation) as e:
            db.rollback()
            message = str(e)

        except Exception as e:
            db.rollback()
            print("INVENTORY ERROR:", repr(e))
            message = "Could not add material. Please check the details."

    # Get raw material stock
    cursor.execute("""
        SELECT *
        FROM raw_materials
        ORDER BY material_id DESC
    """)

    materials = cursor.fetchall()

    # Get finished product stock
    cursor.execute("""
        SELECT *
        FROM products
        ORDER BY product_id DESC
    """)

    products = cursor.fetchall()

    # Get complete stock movement history
    cursor.execute("""
        SELECT
            sm.movement_id,
            sm.material_id,
            sm.product_id,
            sm.movement_type,
            sm.quantity,
            sm.movement_date,
            sm.reference_note,
            rm.material_name,
            p.product_name
        FROM stock_movements sm

        LEFT JOIN raw_materials rm
            ON sm.material_id = rm.material_id

        LEFT JOIN products p
            ON sm.product_id = p.product_id

        ORDER BY sm.movement_id DESC
    """)

    movements = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "inventory.html",
        materials=materials,
        products=products,
        movements=movements,
        message=message,
        role=session.get("role")
    )

# ==============================
# PRODUCTION COST CALCULATION
# ==============================

@app.route("/cost", methods=["GET", "POST"])
@login_required
def cost():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":

        product_id = request.form["product_id"]
        material = float(request.form["material_cost"])
        labour = float(request.form["labour_cost"])
        electricity = float(request.form["electricity_cost"])
        other = float(request.form["other_cost"])
        quantity = int(request.form["production_quantity"])

        if quantity <= 0:
            cursor.close()
            db.close()
            return "Production quantity must be greater than zero.", 400

        total = material + labour + electricity + other
        per_packet = total / quantity

        cursor.execute("""
            INSERT INTO production_costs
            (product_id, material_cost, labour_cost,
             electricity_cost, other_cost, production_quantity,
             total_cost, cost_per_packet)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            product_id,
            material,
            labour,
            electricity,
            other,
            quantity,
            total,
            per_packet
        ))

        db.commit()

        cursor.close()
        db.close()

        return redirect("/cost")

    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()

    cursor.execute("""
        SELECT production_costs.*, products.product_name
        FROM production_costs
        JOIN products
        ON production_costs.product_id = products.product_id
        ORDER BY cost_id DESC
    """)

    records = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "cost.html",
        products=products,
        records=records
    )


# ==============================
# SALES AND STOCK REPORTS
# ==============================

@app.route("/reports")
@login_required
def reports():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total FROM customers")
    customers = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM products")
    products = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM sales_orders")
    orders = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COALESCE(SUM(total_amount), 0) AS total
        FROM sales_orders
    """)

    sales_total = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT product_name, quantity
        FROM products
    """)

    product_stock = cursor.fetchall()

    cursor.execute("""
        SELECT material_name, quantity, unit
        FROM raw_materials
    """)

    material_stock = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "reports.html",
        customers=customers,
        products=products,
        orders=orders,
        sales=sales_total,
        product_stock=product_stock,
        material_stock=material_stock
    )


# ==============================
# RAW MATERIAL PURCHASE MANAGEMENT
# ==============================

@app.route("/purchases", methods=["GET", "POST"])
@role_required("Admin", "Manager")
def purchases():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    message = request.args.get("message", "")

    if request.method == "POST":

        try:
            supplier_name = request.form["supplier_name"].strip()
            invoice_number = request.form.get("invoice_number", "").strip()
            purchase_date = request.form["purchase_date"]
            material_id = int(request.form["material_id"])
            quantity = Decimal(request.form["quantity"])
            unit_price = Decimal(request.form["unit_price"])

            if not supplier_name:
                raise ValueError("Supplier name is required.")

            if quantity <= 0:
                raise ValueError("Quantity must be greater than zero.")

            if unit_price < 0:
                raise ValueError("Unit price cannot be negative.")

            # Validate purchase date
            date.fromisoformat(purchase_date)

            total_amount = (
                quantity * unit_price
            ).quantize(Decimal("0.01"))

            # Start database transaction
            db.start_transaction()

            # Check and lock raw material record
            cursor.execute("""
                SELECT material_id, material_name
                FROM raw_materials
                WHERE material_id = %s
                FOR UPDATE
            """, (material_id,))

            material = cursor.fetchone()

            if material is None:
                raise ValueError("Selected raw material does not exist.")

            # Save purchase details
            cursor.execute("""
                INSERT INTO purchases
                (supplier_name, invoice_number, purchase_date, total_amount)
                VALUES (%s, %s, %s, %s)
            """, (
                supplier_name,
                invoice_number or None,
                purchase_date,
                total_amount
            ))

            purchase_id = cursor.lastrowid

            # Save purchased material details
            cursor.execute("""
                INSERT INTO purchase_items
                (purchase_id, material_id, quantity, unit_price)
                VALUES (%s, %s, %s, %s)
            """, (
                purchase_id,
                material_id,
                quantity,
                unit_price
            ))

            # Increase raw material stock
            cursor.execute("""
                UPDATE raw_materials
                SET quantity = COALESCE(quantity, 0) + %s
                WHERE material_id = %s
            """, (quantity, material_id))

            # Record stock movement
            cursor.execute("""
                INSERT INTO stock_movements
                (material_id, movement_type, quantity, reference_note)
                VALUES (%s, %s, %s, %s)
            """, (
                material_id,
                "PURCHASE_IN",
                quantity,
                f"Purchase ID: {purchase_id}"
            ))

            # Record audit trail
            cursor.execute("""
                INSERT INTO audit_trail
                (user_id, action, details)
                VALUES (%s, %s, %s)
            """, (
                session["user_id"],
                "Raw Material Purchase",
                f"Purchase ID {purchase_id}: "
                f"{material['material_name']}, quantity {quantity}"
            ))

            db.commit()

            return redirect(url_for(
                "purchases",
                message="Purchase saved and stock updated successfully!"
            ))

        except (ValueError, InvalidOperation):
            db.rollback()
            message = "Please enter valid purchase details."

        except Exception:
            db.rollback()
            message = "Purchase could not be saved. Please check the details."

    # Get raw materials for dropdown
    cursor.execute("""
        SELECT material_id, material_name, quantity, unit
        FROM raw_materials
        ORDER BY material_name
    """)

    materials = cursor.fetchall()

    # Get purchase history
    cursor.execute("""
        SELECT
            p.purchase_id,
            p.supplier_name,
            p.invoice_number,
            p.purchase_date,
            p.total_amount,
            GROUP_CONCAT(
                CONCAT(r.material_name, ' (', pi.quantity, ' ', r.unit, ')')
                SEPARATOR ', '
            ) AS materials
        FROM purchases p
        LEFT JOIN purchase_items pi
            ON p.purchase_id = pi.purchase_id
        LEFT JOIN raw_materials r
            ON pi.material_id = r.material_id
        GROUP BY
            p.purchase_id,
            p.supplier_name,
            p.invoice_number,
            p.purchase_date,
            p.total_amount
        ORDER BY p.purchase_id DESC
    """)

    purchase_list = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "purchases.html",
        materials=materials,
        purchases=purchase_list,
        message=message
    )


# ==============================
# BILL OF MATERIALS MANAGEMENT
# ==============================

@app.route("/bom", methods=["GET", "POST"])
@role_required("Admin", "Manager")
def bom_management():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    message = request.args.get("message", "")

    # Get products
    cursor.execute("""
        SELECT product_id, product_name
        FROM products
        ORDER BY product_name
    """)
    products = cursor.fetchall()

    # Get raw materials
    cursor.execute("""
        SELECT material_id, material_name, unit
        FROM raw_materials
        ORDER BY material_name
    """)
    materials = cursor.fetchall()

    if request.method == "POST":

        try:
            product_id = int(request.form["product_id"])
            recipe_name = request.form["recipe_name"].strip()

            selected_items = []

            # Read quantities entered for each material
            for material in materials:

                field_name = f"quantity_{material['material_id']}"
                entered_quantity = request.form.get(field_name, "").strip()

                if entered_quantity == "":
                    continue

                required_quantity = Decimal(entered_quantity)

                if required_quantity < 0:
                    raise ValueError("Quantity cannot be negative.")

                if required_quantity > 0:
                    selected_items.append((
                        material["material_id"],
                        required_quantity
                    ))

            if not recipe_name:
                raise ValueError("Recipe name is required.")

            if not selected_items:
                raise ValueError("Enter at least one material quantity.")


            # Check product
            cursor.execute("""
                SELECT product_id
                FROM products
                WHERE product_id = %s
            """, (product_id,))

            if cursor.fetchone() is None:
                raise ValueError("Product not found.")

            # Create BOM recipe
            cursor.execute("""
                INSERT INTO bom (product_id, recipe_name)
                VALUES (%s, %s)
            """, (product_id, recipe_name))

            bom_id = cursor.lastrowid

            # Save recipe materials
            for material_id, required_quantity in selected_items:

                cursor.execute("""
                    INSERT INTO bom_items
                    (bom_id, material_id, required_quantity)
                    VALUES (%s, %s, %s)
                """, (
                    bom_id,
                    material_id,
                    required_quantity
                ))

            # Audit record
            cursor.execute("""
                INSERT INTO audit_trail
                (user_id, action, details)
                VALUES (%s, %s, %s)
            """, (
                session["user_id"],
                "BOM Created",
                f"BOM ID {bom_id}: {recipe_name}"
            ))

            db.commit()

            return redirect(url_for(
                "bom_management",
                message="Recipe saved successfully!"
            ))

        except Exception as e:
                db.rollback()
                print("BOM SAVE ERROR:", repr(e))
                message = f"Could not save recipe: {e}"
    # Get saved BOM recipes
    cursor.execute("""
        SELECT
            b.bom_id,
            b.recipe_name,
            p.product_name,
            GROUP_CONCAT(
                CONCAT(
                    r.material_name,
                    ' - ',
                    bi.required_quantity,
                    ' ',
                    r.unit
                )
                SEPARATOR ', '
            ) AS ingredients
        FROM bom b
        JOIN products p
            ON b.product_id = p.product_id
        JOIN bom_items bi
            ON b.bom_id = bi.bom_id
        JOIN raw_materials r
            ON bi.material_id = r.material_id
        GROUP BY
            b.bom_id,
            b.recipe_name,
            p.product_name
        ORDER BY b.bom_id DESC
    """)

    recipes = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "bom.html",
        products=products,
        materials=materials,
        recipes=recipes,
        message=message
    )


@app.route("/payments", methods=["GET", "POST"])
@role_required("Admin", "Manager")
def payments():

    db = get_db()
    cursor = db.cursor(dictionary=True)
    message = ""

    if request.method == "POST":
        try:
            order_id = int(request.form["order_id"])
            amount = Decimal(request.form["amount"])
            payment_date = request.form["payment_date"]
            payment_method = request.form["payment_method"]
            notes = request.form.get("notes", "")

            if amount <= 0:
                raise ValueError("Payment amount must be greater than zero.")

            cursor.execute("""
                SELECT total_amount
                FROM sales_orders
                WHERE order_id = %s
            """, (order_id,))

            order = cursor.fetchone()

            if not order:
                raise ValueError("Invalid sales order.")

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) AS paid
                FROM payments
                WHERE order_id = %s
            """, (order_id,))

            paid = Decimal(str(cursor.fetchone()["paid"]))
            total = Decimal(str(order["total_amount"]))

            if amount > total - paid:
                raise ValueError("Payment cannot exceed the outstanding balance.")

            cursor.execute("""
                INSERT INTO payments
                (order_id, payment_date, amount, payment_method, notes)
                VALUES (%s, %s, %s, %s, %s)
            """, (order_id, payment_date, amount,
                  payment_method, notes))

            cursor.execute("""
                INSERT INTO audit_trail (user_id, action, details)
                VALUES (%s, %s, %s)
            """, (
                session["user_id"],
                "Payment Recorded",
                f"Order ID: {order_id}, Amount: {amount}"
            ))

            db.commit()
            message = "Payment recorded successfully!"

        except (ValueError, InvalidOperation, KeyError) as e:
            db.rollback()
            message = str(e)

        except Exception:
            db.rollback()
            message = "Unable to record payment. Please check the entered details."

    cursor.execute("""
        SELECT
            so.order_id,
            so.total_amount,
            c.customer_name,
            COALESCE(SUM(p.amount), 0) AS paid_amount,
            so.total_amount - COALESCE(SUM(p.amount), 0) AS balance
        FROM sales_orders so
        JOIN customers c ON so.customer_id = c.customer_id
        LEFT JOIN payments p ON so.order_id = p.order_id
        GROUP BY so.order_id, so.total_amount, c.customer_name
        ORDER BY so.order_id DESC
    """)

    orders = cursor.fetchall()

    cursor.execute("""
        SELECT p.*, c.customer_name
        FROM payments p
        JOIN sales_orders so ON p.order_id = so.order_id
        JOIN customers c ON so.customer_id = c.customer_id
        ORDER BY p.payment_id DESC
    """)

    payment_history = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "payments.html",
        orders=orders,
        payment_history=payment_history,
        message=message,
        today=date.today().isoformat()
    )


# ==============================
# SALES ORDER APPROVAL
# ==============================

@app.route("/approvals", methods=["GET", "POST"])
@role_required("Admin", "Manager")
def approvals():

    if session.get("role") not in ["Admin", "Manager"]:
        return "You do not have permission to approve orders.", 403

    db = get_db()
    cursor = db.cursor(dictionary=True)
    message = ""

    if request.method == "POST":
        try:
            order_id = int(request.form["order_id"])
            action = request.form["action"]
            approval_note = request.form.get("approval_note", "").strip()

            if action not in ["approve", "reject"]:
                raise ValueError("Invalid approval action.")

            db.start_transaction()

            cursor.execute("""
                SELECT order_id, product_id, quantity, order_status
                FROM sales_orders
                WHERE order_id = %s
                FOR UPDATE
            """, (order_id,))
            order = cursor.fetchone()

            if order is None:
                raise ValueError("Sales order not found.")

            if order["order_status"] != "Pending":
                raise ValueError("This order has already been processed.")

            if action == "approve":
                cursor.execute("""
                    SELECT quantity
                    FROM products
                    WHERE product_id = %s
                    FOR UPDATE
                """, (order["product_id"],))
                product = cursor.fetchone()

                if product is None:
                    raise ValueError("Product not found.")

                if order["quantity"] > product["quantity"]:
                    raise ValueError("Not enough stock to approve this order.")

                cursor.execute("""
                    UPDATE products
                    SET quantity = quantity - %s
                    WHERE product_id = %s
                """, (order["quantity"], order["product_id"]))

                cursor.execute("""
                    INSERT INTO stock_movements
                    (product_id, movement_type, quantity, reference_note)
                    VALUES (%s, %s, %s, %s)
                """, (
                    order["product_id"],
                    "SALES_OUT",
                    order["quantity"],
                    f"Approved Sales Order ID: {order_id}"
                ))

                new_status = "Approved"
                message = "Sales order approved successfully!"

            else:
                new_status = "Rejected"
                message = "Sales order rejected successfully."

            cursor.execute("""
                UPDATE sales_orders
                SET order_status = %s,
                    approved_by = %s,
                    approved_at = NOW(),
                    approval_note = %s
                WHERE order_id = %s
            """, (
                new_status,
                session["user_id"],
                approval_note or None,
                order_id
            ))

            cursor.execute("""
                INSERT INTO audit_trail (user_id, action, details)
                VALUES (%s, %s, %s)
            """, (
                session["user_id"],
                f"Sales Order {new_status}",
                f"Order ID: {order_id}. {approval_note}"
            ))

            db.commit()

        except (ValueError, InvalidOperation, KeyError) as e:
            db.rollback()
            message = str(e)

        except Exception as e:
            db.rollback()
            print("APPROVAL ERROR:", repr(e))
            message = "Could not process the sales order. Please check the server error."

    cursor.execute("""
        SELECT
            s.order_id,
            s.order_date,
            s.quantity,
            s.total_amount,
            s.order_status,
            s.approval_note,
            c.customer_name,
            p.product_name,
            p.quantity AS available_stock,
            a.username AS approved_by_name
        FROM sales_orders s
        JOIN customers c ON s.customer_id = c.customer_id
        JOIN products p ON s.product_id = p.product_id
        LEFT JOIN admin_users a ON s.approved_by = a.user_id
        ORDER BY s.order_id ASC
    """)
    orders = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "approvals.html",
        orders=orders,
        message=message
    )

# ==============================
# PDF INVOICE GENERATION
# ==============================

@app.route("/invoice/<int:order_id>")
@login_required
def generate_invoice(order_id):

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            s.order_id,
            s.order_date,
            s.quantity,
            s.total_amount,
            s.order_status,
            c.customer_name,
            c.phone,
            c.address,
            p.product_name,
            p.price,
            p.gst_rate
        FROM sales_orders s
        JOIN customers c
            ON s.customer_id = c.customer_id
        JOIN products p
            ON s.product_id = p.product_id
        WHERE s.order_id = %s
    """, (order_id,))

    order = cursor.fetchone()

    cursor.close()
    db.close()

    if order is None:
        return "Order not found.", 404

    # Only approved orders can have invoices
    if order["order_status"] != "Approved":
        return "Invoice can be generated only for approved orders.", 400

    # Calculate GST
    subtotal = Decimal(str(order["total_amount"]))
    gst_rate = Decimal(str(order["gst_rate"]))

    gst_amount = (
        subtotal * gst_rate / Decimal("100")
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )

    cgst = (
        gst_amount / Decimal("2")
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )

    sgst = gst_amount - cgst
    grand_total = subtotal + gst_amount

    # Create PDF in memory
    buffer = BytesIO()

    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Company heading
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(50, height - 55, "SNACKS FACTORY")

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, height - 90, "GST INVOICE")

    # Invoice details
    pdf.setFont("Helvetica", 11)
    pdf.drawString(50, height - 130, f"Invoice No: {order['order_id']}")
    pdf.drawString(50, height - 150, f"Date: {order['order_date']}")

    # Customer details
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, height - 190, "Customer Details")

    pdf.setFont("Helvetica", 11)
    pdf.drawString(
        50, height - 215,
        f"Name: {order['customer_name']}"
    )
    pdf.drawString(
        50, height - 235,
        f"Phone: {order['phone'] or 'Not provided'}"
    )
    pdf.drawString(
        50, height - 255,
        f"Address: {order['address'] or 'Not provided'}"
    )

    # Product table heading
    y = height - 310

    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, "Product")
    pdf.drawString(280, y, "Quantity")
    pdf.drawString(370, y, "Price")
    pdf.drawString(470, y, "Amount")

    pdf.line(50, y - 8, 550, y - 8)

    # Product details
    y = y - 35

    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, y, str(order["product_name"]))
    pdf.drawString(280, y, str(order["quantity"]))
    pdf.drawString(370, y, f"Rs. {order['price']}")
    pdf.drawString(470, y, f"Rs. {subtotal}")

    # GST details
    y = y - 65

    pdf.line(350, y + 20, 550, y + 20)

    pdf.setFont("Helvetica", 11)
    pdf.drawString(350, y, "Subtotal:")
    pdf.drawRightString(550, y, f"Rs. {subtotal}")

    y = y - 22
    pdf.drawString(350, y, f"GST ({gst_rate}%):")
    pdf.drawRightString(550, y, f"Rs. {gst_amount}")

    y = y - 22
    pdf.drawString(350, y, "CGST:")
    pdf.drawRightString(550, y, f"Rs. {cgst}")

    y = y - 22
    pdf.drawString(350, y, "SGST:")
    pdf.drawRightString(550, y, f"Rs. {sgst}")

    y = y - 35

    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(350, y, "Grand Total:")
    pdf.drawRightString(550, y, f"Rs. {grand_total}")

    # Footer
    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, 80, "Thank you for your purchase!")

    pdf.save()

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Invoice_{order_id}.pdf",
        mimetype="application/pdf"
    )


# ==============================
# MONTHLY AUDIT REPORTS
# ==============================

@app.route("/audit-reports")
@role_required("Admin")
def audit_reports():

    db = get_db()
    cursor = db.cursor(dictionary=True)

    selected_month = request.args.get(
        "month",
        date.today().strftime("%Y-%m")
    )

    try:
        datetime.strptime(selected_month, "%Y-%m")
    except ValueError:
        selected_month = date.today().strftime("%Y-%m")

    cursor.execute("""
        SELECT
            audit_id,
            user_id,
            action,
            details,
            action_date
        FROM audit_trail
        WHERE DATE_FORMAT(action_date, '%Y-%m') = %s
        ORDER BY action_date DESC
    """, (selected_month,))

    audit_records = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "audit_reports.html",
        audit_records=audit_records,
        selected_month=selected_month
    )



# ==============================
# USER MANAGEMENT
# ==============================

@app.route("/users", methods=["GET", "POST"])
@role_required("Admin")
def users():

    # Only Admin can manage users
    if session.get("role") != "Admin":
        return "Access denied. Admin only.", 403

    db = get_db()
    cursor = db.cursor(dictionary=True)

    message = ""

    if request.method == "POST":

        action = request.form.get("action")

        # ADD NEW USER
        if action == "add":

            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            role = request.form.get("role", "")

            if not username or not password:
                message = "Username and password are required."

            elif len(password) < 8:
                message = "Password must contain at least 8 characters."

            elif role not in ["Admin", "Manager", "Staff"]:
                message = "Invalid user role."

            else:

                cursor.execute(
                    "SELECT user_id FROM admin_users WHERE username = %s",
                    (username,)
                )

                existing_user = cursor.fetchone()

                if existing_user:
                    message = "Username already exists."

                else:

                    password_hash = generate_password_hash(password)

                    cursor.execute("""
                        INSERT INTO admin_users
                        (username, password_hash, role, is_active)
                        VALUES (%s, %s, %s, 1)
                    """, (username, password_hash, role))

                    db.commit()

                    message = "New user added successfully."

        # ACTIVATE / DEACTIVATE USER
        elif action == "toggle":

            try:
                user_id = int(request.form.get("user_id", 0))
            except (ValueError, TypeError):
                user_id = 0

            if user_id == session.get("user_id"):
                message = "You cannot deactivate your own account."

            elif user_id <= 0:
                message = "Invalid user."

            else:

                cursor.execute("""
                    SELECT is_active
                    FROM admin_users
                    WHERE user_id = %s
                """, (user_id,))

                selected_user = cursor.fetchone()

                if selected_user:

                    new_status = 0 if selected_user["is_active"] else 1

                    cursor.execute("""
                        UPDATE admin_users
                        SET is_active = %s
                        WHERE user_id = %s
                    """, (new_status, user_id))

                    db.commit()

                    message = "User status updated successfully."

                else:
                    message = "User not found."

    # GET ALL USERS
    cursor.execute("""
        SELECT user_id, username, role, is_active
        FROM admin_users
        ORDER BY user_id DESC
    """)

    user_list = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "users.html",
        user_list=user_list,
        message=message
    )


# ==============================
# RUN APPLICATION
# ==============================

if __name__ == "__main__":
    app.run(debug=True)
