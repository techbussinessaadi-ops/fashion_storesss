import os
from flask import Flask

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

# ✅ SQLite for deploy (temporary). For permanent DB, use Postgres later.
db_path = os.path.join("/tmp", "store.db")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", f"sqlite:///{db_path}")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
import os, uuid
from datetime import datetime, date

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, abort
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ---------------- APP CONFIG ----------------
app = Flask(__name__)
app.secret_key = "change_this_secret_key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}

db = SQLAlchemy(app)

# ---------------- MODELS ----------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(140), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    # profile
    full_name = db.Column(db.String(140), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    address = db.Column(db.String(300), nullable=True)
    city = db.Column(db.String(80), nullable=True)
    pincode = db.Column(db.String(20), nullable=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    discount_price = db.Column(db.Integer, nullable=True)
    stock = db.Column(db.Integer, nullable=False, default=10)
    rating = db.Column(db.Float, nullable=False, default=4.3)
    sizes = db.Column(db.String(80), nullable=False, default="S,M,L,XL")
    colors = db.Column(db.String(120), nullable=False, default="Black,White,Navy")
    description = db.Column(db.Text, nullable=False, default="Premium quality clothing.")
    badge = db.Column(db.String(40), nullable=True)  # New/Hot/Best
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ProductImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, index=True, nullable=False)
    image_path = db.Column(db.String(300), nullable=False)  # uploads/xxx.webp
    is_primary = db.Column(db.Boolean, default=False)

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, index=True, nullable=False)
    product_id = db.Column(db.Integer, index=True, nullable=False)
    qty = db.Column(db.Integer, nullable=False, default=1)
    size = db.Column(db.String(10), nullable=False, default="M")
    color = db.Column(db.String(30), nullable=False, default="Black")

class Wishlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, index=True, nullable=False)
    product_id = db.Column(db.Integer, index=True, nullable=False)

class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    kind = db.Column(db.String(10), nullable=False)  # PERCENT / FLAT
    value = db.Column(db.Integer, nullable=False)    # 10 => 10% or ₹10
    min_total = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)
    usage_limit = db.Column(db.Integer, default=999999)
    used_count = db.Column(db.Integer, default=0)
    expiry = db.Column(db.String(20), nullable=True)  # YYYY-MM-DD or None

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, index=True, nullable=False)

    full_name = db.Column(db.String(140), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    city = db.Column(db.String(80), nullable=False)
    pincode = db.Column(db.String(20), nullable=False)

    payment_method = db.Column(db.String(40), nullable=False, default="COD")
    subtotal = db.Column(db.Integer, nullable=False)
    discount = db.Column(db.Integer, nullable=False, default=0)
    total_amount = db.Column(db.Integer, nullable=False)

    coupon_code = db.Column(db.String(30), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="Pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, index=True, nullable=False)
    product_id = db.Column(db.Integer, nullable=False)
    product_name = db.Column(db.String(160), nullable=False)
    price_each = db.Column(db.Integer, nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    size = db.Column(db.String(10), nullable=False)
    color = db.Column(db.String(30), nullable=False)
    line_total = db.Column(db.Integer, nullable=False)

# ---------------- HELPERS ----------------
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def logged_in():
    return "user_id" in session

def current_user():
    if not logged_in():
        return None
    return User.query.get(session["user_id"])

def require_admin():
    u = current_user()
    if not u or not u.is_admin:
        abort(403)

def money(p: Product) -> int:
    return p.discount_price if p.discount_price else p.price

def primary_image_path(product_id: int) -> str:
    img = ProductImage.query.filter_by(product_id=product_id, is_primary=True).first()
    if img:
        return img.image_path
    img = ProductImage.query.filter_by(product_id=product_id).first()
    if img:
        return img.image_path
    return "uploads/placeholder.jpg"

def cart_rows_and_total(user_id: int):
    items = CartItem.query.filter_by(user_id=user_id).all()
    rows = []
    subtotal = 0
    for it in items:
        p = Product.query.get(it.product_id)
        if not p:
            continue
        unit = money(p)
        line = unit * it.qty
        subtotal += line
        rows.append({"item": it, "product": p, "unit": unit, "line": line, "img": primary_image_path(p.id)})
    return rows, subtotal

def wishlist_set(user_id: int):
    ids = db.session.query(Wishlist.product_id).filter_by(user_id=user_id).all()
    return set(x[0] for x in ids)

def parse_date(s: str):
    try:
        return date.fromisoformat(s)
    except:
        return None

def apply_coupon(subtotal: int, code: str):
    """
    returns: (discount_amount, message, coupon_obj or None)
    """
    code = (code or "").strip().upper()
    if not code:
        return 0, None, None

    c = Coupon.query.filter_by(code=code).first()
    if not c or not c.active:
        return 0, "Invalid coupon.", None

    if subtotal < (c.min_total or 0):
        return 0, f"Minimum total ₹{c.min_total} required.", None

    if c.used_count >= c.usage_limit:
        return 0, "Coupon usage limit reached.", None

    if c.expiry:
        d = parse_date(c.expiry)
        if d and date.today() > d:
            return 0, "Coupon expired.", None

    if c.kind == "PERCENT":
        disc = (subtotal * c.value) // 100
    else:
        disc = c.value

    disc = max(0, min(disc, subtotal))
    return disc, f"Coupon applied: -₹{disc}", c

def seed_if_empty():
    db.create_all()

    # default admin
    if User.query.count() == 0:
        admin = User(
            username="admin",
            password_hash=generate_password_hash("admin123"),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin created: admin / admin123")

    # seed coupons
    if Coupon.query.count() == 0:
        db.session.add(Coupon(code="SAVE10", kind="PERCENT", value=10, min_total=500, active=True, usage_limit=1000))
        db.session.add(Coupon(code="FLAT50", kind="FLAT", value=50, min_total=799, active=True, usage_limit=1000))
        db.session.commit()

    # seed products + one image each (placeholder path)
    if Product.query.count() > 0:
        return

    products = [
        dict(name="Classic Black Tee", category="T-Shirts", price=499, discount_price=399, stock=30, rating=4.6,
             sizes="S,M,L,XL", colors="Black,White,Navy", badge="Hot",
             description="Soft cotton premium tee. Breathable fabric, clean fit."),
        dict(name="Oversized Street Tee", category="T-Shirts", price=699, discount_price=None, stock=25, rating=4.4,
             sizes="M,L,XL", colors="Black,White", badge="New",
             description="Oversized streetwear style. Comfort fit for daily wear."),
        dict(name="Formal Sky Shirt", category="Shirts", price=899, discount_price=799, stock=18, rating=4.5,
             sizes="M,L,XL", colors="Sky,White,Navy", badge="Best",
             description="Perfect formal shirt for events. Sharp look, easy iron."),
        dict(name="Denim Jacket", category="Jackets", price=1499, discount_price=1299, stock=12, rating=4.3,
             sizes="M,L,XL", colors="Blue,Black", badge="Hot",
             description="Classic denim jacket. Layer up in style."),
        dict(name="Premium Hoodie", category="Hoodies", price=1199, discount_price=999, stock=20, rating=4.7,
             sizes="M,L,XL", colors="Black,Grey,Navy", badge="Best",
             description="Warm premium hoodie. Soft inner lining."),
        dict(name="Summer Dress", category="Dresses", price=999, discount_price=None, stock=10, rating=4.2,
             sizes="S,M,L", colors="Red,Black,Navy", badge="New",
             description="Comfort summer dress. Lightweight fabric."),
    ]

    for p in products:
        pr = Product(**p)
        db.session.add(pr)
        db.session.commit()  # get ID

        # attach 1 placeholder primary image (you will replace via admin upload)
        img = ProductImage(product_id=pr.id, image_path="uploads/placeholder.jpg", is_primary=True)
        db.session.add(img)
        db.session.commit()

# ---------------- INIT ----------------
with app.app_context():
    seed_if_empty()

# ---------------- ERROR PAGES ----------------
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500

@app.errorhandler(403)
def forbidden(e):
    return "<h2>403 Forbidden</h2><p>Admin access required.</p>", 403

# ---------------- AUTH ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            return render_template("register.html", error="Username & password required.")

        if User.query.filter_by(username=username).first():
            return render_template("register.html", error="Username already exists.")

        u = User(username=username, password_hash=generate_password_hash(password), is_admin=False)
        db.session.add(u)
        db.session.commit()
        flash("Account created! Please login.", "ok")
        return redirect(url_for("login"))

    return render_template("register.html", error=None)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        u = User.query.filter_by(username=username).first()
        if u and check_password_hash(u.password_hash, password):
            session["user_id"] = u.id
            flash("Logged in ✅", "ok")
            return redirect(url_for("store"))

        return render_template("login.html", error="Invalid username or password.")

    return render_template("login.html", error=None)

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "ok")
    return redirect(url_for("login"))

# ---------------- PROFILE + ORDER HISTORY ----------------
@app.route("/profile", methods=["GET", "POST"])
def profile():
    if not logged_in():
        return redirect(url_for("login"))

    u = current_user()
    if request.method == "POST":
        u.full_name = request.form.get("full_name", "").strip()
        u.phone = request.form.get("phone", "").strip()
        u.address = request.form.get("address", "").strip()
        u.city = request.form.get("city", "").strip()
        u.pincode = request.form.get("pincode", "").strip()
        db.session.commit()
        flash("Profile updated ✅", "ok")
        return redirect(url_for("profile"))

    return render_template("profile.html", user=u)

@app.route("/orders")
def orders():
    if not logged_in():
        return redirect(url_for("login"))

    u = current_user()
    orders = Order.query.filter_by(user_id=u.id).order_by(Order.created_at.desc()).all()
    # load items
    data = []
    for o in orders:
        items = OrderItem.query.filter_by(order_id=o.id).all()
        data.append((o, items))
    return render_template("orders.html", data=data, user=u)

# ---------------- STORE (search/filter/sort/pagination) ----------------
@app.route("/")
def store():
    if not logged_in():
        return redirect(url_for("login"))

    u = current_user()
    q = request.args.get("q", "").strip()
    cat = request.args.get("cat", "").strip()
    sort = request.args.get("sort", "new").strip()
    in_stock = request.args.get("in_stock", "").strip()  # "1"
    minp = request.args.get("minp", "").strip()
    maxp = request.args.get("maxp", "").strip()
    minr = request.args.get("minr", "").strip()
    page = int(request.args.get("page", "1") or 1)

    query = Product.query

    if cat:
        query = query.filter_by(category=cat)
    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))
    if in_stock == "1":
        query = query.filter(Product.stock > 0)

    # price filter by effective price
    def eff_price_expr():
        # SQLite: CASE WHEN discount_price IS NOT NULL THEN discount_price ELSE price END
        return db.case((Product.discount_price.isnot(None), Product.discount_price), else_=Product.price)

    if minp.isdigit():
        query = query.filter(eff_price_expr() >= int(minp))
    if maxp.isdigit():
        query = query.filter(eff_price_expr() <= int(maxp))
    try:
        if minr:
            query = query.filter(Product.rating >= float(minr))
    except:
        pass

    if sort == "price_low":
        query = query.order_by(eff_price_expr().asc())
    elif sort == "price_high":
        query = query.order_by(eff_price_expr().desc())
    elif sort == "rating":
        query = query.order_by(Product.rating.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    per_page = 12
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    products = pagination.items

    categories = [c[0] for c in db.session.query(Product.category).distinct().all()]

    rows, _ = cart_rows_and_total(u.id)
    cart_count = sum(r["item"].qty for r in rows)
    wset = wishlist_set(u.id)

    # attach primary image path quickly
    prod_cards = []
    for p in products:
        prod_cards.append({
            "p": p,
            "img": primary_image_path(p.id),
            "in_wishlist": (p.id in wset),
            "effective_price": money(p),
        })

    return render_template(
        "index.html",
        cards=prod_cards,
        categories=categories,
        active_cat=cat,
        q=q,
        sort=sort,
        cart_count=cart_count,
        user=u,
        in_stock=in_stock,
        minp=minp, maxp=maxp, minr=minr,
        pagination=pagination
    )

@app.route("/product/<int:pid>")
def product_detail(pid: int):
    if not logged_in():
        return redirect(url_for("login"))

    u = current_user()
    p = Product.query.get_or_404(pid)
    imgs = ProductImage.query.filter_by(product_id=p.id).order_by(ProductImage.is_primary.desc(), ProductImage.id.asc()).all()
    if not imgs:
        imgs = [ProductImage(product_id=p.id, image_path="uploads/placeholder.jpg", is_primary=True)]

    rows, _ = cart_rows_and_total(u.id)
    cart_count = sum(r["item"].qty for r in rows)
    in_wishlist = Wishlist.query.filter_by(user_id=u.id, product_id=p.id).first() is not None

    return render_template("product.html", p=p, imgs=imgs, cart_count=cart_count, user=u, in_wishlist=in_wishlist)

# ---------------- WISHLIST ----------------
@app.route("/wishlist/toggle/<int:pid>", methods=["POST"])
def wishlist_toggle(pid: int):
    if not logged_in():
        return redirect(url_for("login"))

    u = current_user()
    existing = Wishlist.query.filter_by(user_id=u.id, product_id=pid).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        flash("Removed from wishlist.", "ok")
    else:
        db.session.add(Wishlist(user_id=u.id, product_id=pid))
        db.session.commit()
        flash("Added to wishlist ❤️", "ok")

    return redirect(request.referrer or url_for("store"))

@app.route("/wishlist")
def wishlist_page():
    if not logged_in():
        return redirect(url_for("login"))
    u = current_user()

    items = Wishlist.query.filter_by(user_id=u.id).all()
    cards = []
    for w in items:
        p = Product.query.get(w.product_id)
        if not p:
            continue
        cards.append({"p": p, "img": primary_image_path(p.id), "effective_price": money(p), "in_wishlist": True})

    rows, _ = cart_rows_and_total(u.id)
    cart_count = sum(r["item"].qty for r in rows)
    return render_template("index.html",  # reuse grid page
                           cards=cards, categories=[], active_cat="", q="", sort="new",
                           cart_count=cart_count, user=u,
                           in_stock="", minp="", maxp="", minr="",
                           pagination=None, wishlist_only=True)

# ---------------- CART ----------------
@app.route("/cart")
def cart():
    if not logged_in():
        return redirect(url_for("login"))

    u = current_user()
    rows, subtotal = cart_rows_and_total(u.id)
    return render_template("cart.html", rows=rows, subtotal=subtotal, user=u)

@app.route("/add/<int:pid>", methods=["POST"])
def add_to_cart(pid: int):
    if not logged_in():
        return redirect(url_for("login"))

    u = current_user()
    p = Product.query.get_or_404(pid)
    if p.stock <= 0:
        flash("Out of stock!", "bad")
        return redirect(request.referrer or url_for("store"))

    size = request.form.get("size", "M")
    color = request.form.get("color", "Black")

    existing = CartItem.query.filter_by(user_id=u.id, product_id=pid, size=size, color=color).first()
    if existing:
        existing.qty += 1
    else:
        db.session.add(CartItem(user_id=u.id, product_id=pid, qty=1, size=size, color=color))
    db.session.commit()

    flash("Added to cart ✅", "ok")
    return redirect(request.referrer or url_for("store"))

@app.route("/qty/<int:item_id>", methods=["POST"])
def change_qty(item_id: int):
    if not logged_in():
        return redirect(url_for("login"))

    u = current_user()
    action = request.form.get("action")
    it = CartItem.query.get_or_404(item_id)
    if it.user_id != u.id:
        abort(403)

    if action == "plus":
        it.qty += 1
    elif action == "minus":
        it.qty -= 1
        if it.qty <= 0:
            db.session.delete(it)

    db.session.commit()
    return redirect(url_for("cart"))

@app.route("/remove/<int:item_id>", methods=["POST"])
def remove_item(item_id: int):
    if not logged_in():
        return redirect(url_for("login"))

    u = current_user()
    it = CartItem.query.get_or_404(item_id)
    if it.user_id != u.id:
        abort(403)

    db.session.delete(it)
    db.session.commit()
    flash("Removed.", "ok")
    return redirect(url_for("cart"))

@app.route("/clear", methods=["POST"])
def clear_cart():
    if not logged_in():
        return redirect(url_for("login"))
    u = current_user()

    CartItem.query.filter_by(user_id=u.id).delete()
    db.session.commit()
    flash("Cart cleared.", "ok")
    return redirect(url_for("cart"))

# ---------------- CHECKOUT / COUPONS / ORDERS ----------------
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if not logged_in():
        return redirect(url_for("login"))

    u = current_user()
    rows, subtotal = cart_rows_and_total(u.id)
    if not rows:
        flash("Cart is empty.", "bad")
        return redirect(url_for("store"))

    # prefill profile
    pref = {
        "full_name": u.full_name or "",
        "phone": u.phone or "",
        "address": u.address or "",
        "city": u.city or "",
        "pincode": u.pincode or "",
    }

    # coupon from session
    coupon_code = session.get("coupon_code", "")
    discount, msg, _ = apply_coupon(subtotal, coupon_code)
    total = subtotal - discount

    if request.method == "POST":
        action = request.form.get("action", "place")

        if action == "apply_coupon":
            code = request.form.get("coupon", "").strip().upper()
            d, m, c = apply_coupon(subtotal, code)
            if c:
                session["coupon_code"] = code
                flash(m, "ok")
            else:
                session["coupon_code"] = ""
                flash(m or "Invalid coupon.", "bad")
            return redirect(url_for("checkout"))

        # PLACE ORDER
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        city = request.form.get("city", "").strip()
        pincode = request.form.get("pincode", "").strip()
        payment = request.form.get("payment", "COD").strip()

        if not all([full_name, phone, address, city, pincode]):
            flash("Please fill all fields.", "bad")
            return render_template("checkout.html", rows=rows, subtotal=subtotal, discount=discount, total=total,
                                   coupon=coupon_code, pref=pref, user=u)

        # recompute coupon
        coupon_code = session.get("coupon_code", "")
        discount, _, coupon_obj = apply_coupon(subtotal, coupon_code)
        total = subtotal - discount

        # Create order
        o = Order(
            user_id=u.id,
            full_name=full_name, phone=phone, address=address, city=city, pincode=pincode,
            payment_method=payment,
            subtotal=subtotal, discount=discount, total_amount=total,
            coupon_code=coupon_code or None,
            status="Pending"
        )
        db.session.add(o)
        db.session.commit()

        # Create items + stock reduce
        for r in rows:
            p = r["product"]
            it = r["item"]
            unit = r["unit"]
            line = r["line"]
            if p.stock < it.qty:
                flash(f"Not enough stock for {p.name}.", "bad")
                return redirect(url_for("cart"))
            p.stock -= it.qty
            db.session.add(OrderItem(
                order_id=o.id,
                product_id=p.id,
                product_name=p.name,
                price_each=unit,
                qty=it.qty,
                size=it.size,
                color=it.color,
                line_total=line
            ))

        # coupon usage count
        if coupon_obj:
            coupon_obj.used_count += 1

        # clear cart + coupon
        CartItem.query.filter_by(user_id=u.id).delete()
        session["coupon_code"] = ""
        db.session.commit()

        flash("Order placed 🎉", "ok")
        return redirect(url_for("success", order_id=o.id))

    return render_template("checkout.html", rows=rows, subtotal=subtotal, discount=discount, total=total,
                           coupon=coupon_code, pref=pref, user=u)

@app.route("/success")
def success():
    if not logged_in():
        return redirect(url_for("login"))
    return render_template("success.html", order_id=request.args.get("order_id"), user=current_user())

# ---------------- ADMIN ----------------
@app.route("/admin")
def admin_dashboard():
    if not logged_in():
        return redirect(url_for("login"))
    require_admin()

    # stats
    product_count = Product.query.count()
    order_count = Order.query.count()
    pending = Order.query.filter_by(status="Pending").count()
    low_stock = Product.query.filter(Product.stock <= 5).count()

    # revenue by last 7 days (simple)
    days = []
    revenue = []
    for i in range(6, -1, -1):
        d = date.today().toordinal() - i
        dt = date.fromordinal(d)
        start = datetime(dt.year, dt.month, dt.day, 0, 0, 0)
        end = datetime(dt.year, dt.month, dt.day, 23, 59, 59)
        s = db.session.query(db.func.sum(Order.total_amount)).filter(Order.created_at >= start, Order.created_at <= end).scalar()
        days.append(dt.strftime("%d-%b"))
        revenue.append(int(s or 0))

    return render_template("admin_dashboard.html",
                           product_count=product_count, order_count=order_count, pending=pending,
                           low_stock=low_stock, days=days, revenue=revenue, user=current_user())

@app.route("/admin/products")
def admin_products():
    if not logged_in():
        return redirect(url_for("login"))
    require_admin()

    products = Product.query.order_by(Product.created_at.desc()).all()
    # attach primary image
    rows = []
    for p in products:
        rows.append({"p": p, "img": primary_image_path(p.id)})
    return render_template("admin_products.html", rows=rows, user=current_user())

@app.route("/admin/products/new", methods=["GET", "POST"])
def admin_product_new():
    if not logged_in():
        return redirect(url_for("login"))
    require_admin()

    if request.method == "POST":
        return save_product(None)
    return render_template("admin_product_form.html", p=None, imgs=[], user=current_user())

@app.route("/admin/products/edit/<int:pid>", methods=["GET", "POST"])
def admin_product_edit(pid):
    if not logged_in():
        return redirect(url_for("login"))
    require_admin()

    p = Product.query.get_or_404(pid)
    imgs = ProductImage.query.filter_by(product_id=p.id).order_by(ProductImage.is_primary.desc(), ProductImage.id.asc()).all()

    if request.method == "POST":
        return save_product(p)

    return render_template("admin_product_form.html", p=p, imgs=imgs, user=current_user())

def save_product(p: Product | None):
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    price = int(request.form.get("price", "0") or 0)
    discount_price = request.form.get("discount_price", "").strip()
    discount_price = int(discount_price) if discount_price else None
    stock = int(request.form.get("stock", "0") or 0)
    rating = float(request.form.get("rating", "4.3") or 4.3)
    sizes = request.form.get("sizes", "S,M,L,XL").strip()
    colors = request.form.get("colors", "Black,White").strip()
    description = request.form.get("description", "Premium quality.").strip()
    badge = request.form.get("badge", "").strip() or None

    if not name or not category or price <= 0:
        flash("Name, category and price required.", "bad")
        return redirect(request.url)

    if p is None:
        p = Product(
            name=name, category=category, price=price, discount_price=discount_price,
            stock=stock, rating=rating, sizes=sizes, colors=colors,
            description=description, badge=badge
        )
        db.session.add(p)
        db.session.commit()
        # ensure at least one image row
        db.session.add(ProductImage(product_id=p.id, image_path="uploads/placeholder.jpg", is_primary=True))
        db.session.commit()
    else:
        p.name = name
        p.category = category
        p.price = price
        p.discount_price = discount_price
        p.stock = stock
        p.rating = rating
        p.sizes = sizes
        p.colors = colors
        p.description = description
        p.badge = badge
        db.session.commit()

    # multi image upload: field name="images" multiple
    files = request.files.getlist("images")
    made_primary = False

    for f in files:
        if not f or not f.filename:
            continue
        if not allowed_file(f.filename):
            flash("Invalid image type. Use png/jpg/jpeg/webp.", "bad")
            return redirect(request.url)

        ext = f.filename.rsplit(".", 1)[1].lower()
        safe = secure_filename(f.filename.rsplit(".", 1)[0])
        new_name = f"{safe}_{uuid.uuid4().hex[:8]}.{ext}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], new_name)
        f.save(save_path)

        # if this is first real upload -> set as primary (remove old primary flag)
        if not made_primary:
            ProductImage.query.filter_by(product_id=p.id).update({ProductImage.is_primary: False})
            db.session.commit()
            db.session.add(ProductImage(product_id=p.id, image_path=f"uploads/{new_name}", is_primary=True))
            made_primary = True
        else:
            db.session.add(ProductImage(product_id=p.id, image_path=f"uploads/{new_name}", is_primary=False))

        db.session.commit()

    flash("Product saved ✅", "ok")
    return redirect(url_for("admin_products"))

@app.route("/admin/products/img/<int:img_id>/primary", methods=["POST"])
def admin_set_primary(img_id):
    if not logged_in():
        return redirect(url_for("login"))
    require_admin()

    img = ProductImage.query.get_or_404(img_id)
    ProductImage.query.filter_by(product_id=img.product_id).update({ProductImage.is_primary: False})
    img.is_primary = True
    db.session.commit()
    flash("Primary image updated.", "ok")
    return redirect(request.referrer or url_for("admin_products"))

@app.route("/admin/products/img/<int:img_id>/delete", methods=["POST"])
def admin_delete_image(img_id):
    if not logged_in():
        return redirect(url_for("login"))
    require_admin()

    img = ProductImage.query.get_or_404(img_id)
    pid = img.product_id

    # prevent deleting last image
    count = ProductImage.query.filter_by(product_id=pid).count()
    if count <= 1:
        flash("At least one image is required.", "bad")
        return redirect(request.referrer or url_for("admin_products"))

    db.session.delete(img)
    db.session.commit()

    # ensure one primary
    if ProductImage.query.filter_by(product_id=pid, is_primary=True).count() == 0:
        first = ProductImage.query.filter_by(product_id=pid).first()
        first.is_primary = True
        db.session.commit()

    flash("Image deleted.", "ok")
    return redirect(request.referrer or url_for("admin_products"))

@app.route("/admin/products/delete/<int:pid>", methods=["POST"])
def admin_product_delete(pid):
    if not logged_in():
        return redirect(url_for("login"))
    require_admin()

    ProductImage.query.filter_by(product_id=pid).delete()
    Wishlist.query.filter_by(product_id=pid).delete()
    CartItem.query.filter_by(product_id=pid).delete()
    p = Product.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    flash("Product deleted.", "ok")
    return redirect(url_for("admin_products"))

@app.route("/admin/coupons", methods=["GET", "POST"])
def admin_coupons():
    if not logged_in():
        return redirect(url_for("login"))
    require_admin()

    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        kind = request.form.get("kind", "PERCENT").strip().upper()
        value = int(request.form.get("value", "0") or 0)
        min_total = int(request.form.get("min_total", "0") or 0)
        usage_limit = int(request.form.get("usage_limit", "999999") or 999999)
        expiry = request.form.get("expiry", "").strip() or None
        active = True if request.form.get("active") == "on" else False

        if not code or value <= 0 or kind not in ("PERCENT", "FLAT"):
            flash("Invalid coupon fields.", "bad")
            return redirect(url_for("admin_coupons"))

        if Coupon.query.filter_by(code=code).first():
            flash("Coupon code already exists.", "bad")
            return redirect(url_for("admin_coupons"))

        db.session.add(Coupon(code=code, kind=kind, value=value, min_total=min_total,
                              active=active, usage_limit=usage_limit, expiry=expiry))
        db.session.commit()
        flash("Coupon created ✅", "ok")
        return redirect(url_for("admin_coupons"))

    coupons = Coupon.query.order_by(Coupon.id.desc()).all()
    return render_template("admin_coupons.html", coupons=coupons, user=current_user())

@app.route("/admin/coupons/toggle/<int:cid>", methods=["POST"])
def admin_coupon_toggle(cid):
    if not logged_in():
        return redirect(url_for("login"))
    require_admin()

    c = Coupon.query.get_or_404(cid)
    c.active = not c.active
    db.session.commit()
    flash("Coupon updated.", "ok")
    return redirect(url_for("admin_coupons"))

@app.route("/admin/orders")
def admin_orders():
    if not logged_in():
        return redirect(url_for("login"))
    require_admin()

    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template("admin_orders.html", orders=orders, user=current_user())

@app.route("/admin/orders/status/<int:oid>", methods=["POST"])
def admin_order_status(oid):
    if not logged_in():
        return redirect(url_for("login"))
    require_admin()

    o = Order.query.get_or_404(oid)
    status = request.form.get("status", "Pending")
    o.status = status
    db.session.commit()
    flash("Order status updated.", "ok")
    return redirect(url_for("admin_orders"))
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)