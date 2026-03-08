# app/models.py

from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    Boolean,
    Date,
    DateTime,
    Numeric,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, ENUM, UUID
from sqlalchemy.sql import func
from app.database import Base
from sqlalchemy import Float

# If you have PostGIS + geoalchemy2 installed (recommended)
try:
    from geoalchemy2 import Geometry
except ImportError:
    # Fallback: treat geometry as generic Text if geoalchemy2 isn't installed
    # Create a wrapper that accepts but ignores the srid parameter
    class Geometry(Text):
        def __init__(self, geometry_type="POLYGON", srid=4326, **kwargs):
            super().__init__(**kwargs)
            self.geometry_type = geometry_type
            self.srid = srid


# ---------- PostgreSQL ENUM Types (mapped to existing DB enums) ----------

billing_interval_enum = ENUM(
    "MONTHLY",
    "QUARTERLY",
    "YEARLY",
    name="billing_interval",
    create_type=False,
)

bwg_status_enum = ENUM(
    "signup",
    "pending_registration",
    "pending_approval",
    "approved",
    "rejected",
    name="bwg_status",
    create_type=False,
)

contract_status_enum = ENUM(
    "ACTIVE",
    "PAUSED",
    "CANCELLED",
    name="contract_status",
    create_type=False,
)

grievance_category_enum = ENUM(
    "Collection Delay",
    #"Weight Discrepancy",
    "Missed Pickup",
    #"Billing/Payment Issue",
    #"Vehicle Mismanagement",
    "Other",
    name="grievance_category",
    create_type=False,
)

grievance_status_enum = ENUM(
    "Open",
    "In Progress",
    "Resolved",
    "Closed",
    name="grievance_status",
    create_type=False,
)

invoice_status_enum = ENUM(
    "DRAFT",
    "UNPAID",
    "PAID",
    "OVERDUE",
    "VOID",
    name="invoice_status",
    create_type=False,
)

notification_type_enum = ENUM(
    "PAYMENT",
    "GRIEVANCE",
    "SYSTEM",
    name="notification_type",
    create_type=False,
)

pickup_status_enum = ENUM(
    "PENDING",
    "DONE",
    "MISSED",
    name="pickup_status",
    create_type=False,
)

transaction_status_enum = ENUM(
    "PENDING",
    "SUCCESSFUL",
    "FAILED",
    name="transaction_status",
    create_type=False,
)


# ------------------------------- Core Tables -------------------------------


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), nullable=False)
    password_hash = Column(Text, nullable=False)
    gmail = Column(String(255), unique=True)


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)

    wards = relationship("Ward", back_populates="zone", cascade="all, delete-orphan")
    bwgs = relationship("Bwg", back_populates="zone_ref")


class Ward(Base):
    __tablename__ = "wards"

    id = Column(Integer, primary_key=True)
    ward_number = Column(Integer, nullable=False)
    ward_name = Column(String(255), nullable=False)
    zone_id = Column(Integer, ForeignKey("zones.id", ondelete="CASCADE"))
    geom = Column(Geometry("MULTIPOLYGON", srid=4326))

    zone = relationship("Zone", back_populates="wards")
    bwgs = relationship("Bwg", back_populates="ward_ref")
    drivers = relationship("Driver", back_populates="ward")
    vehicles = relationship("Vehicle", back_populates="ward")
    registrations = relationship("Registration", back_populates="ward")


class BswmlUser(Base):
    __tablename__ = "bswml_user"

    bswml_id = Column(String(20), primary_key=True)
    name = Column(String(100), nullable=False)
    gmail = Column(String(150), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    phone = Column(String(20))
    username = Column(String(100), nullable=False, unique=True)
    govt_id = Column(String(100))


class Bwg(Base):
    __tablename__ = "bwg"

    id = Column(String(10), primary_key=True)
    username = Column(String(255))
    password = Column(String(255))
    organization = Column(String(255))
    phone = Column(String(20))
    person = Column(String(100))
    location = Column(String(255), nullable=False, default="https://maps.google.com")
    address = Column(String(255))
    generator_type = Column(Text)
    email = Column(Text)
    waste_types = Column(JSONB)
    id_proof_url = Column(Text)
    org_photo_url = Column(Text)
    created_at = Column(DateTime(timezone=True))
    inspection_date = Column(DateTime(timezone=True))
    ward_number = Column(Integer)
    ward_name = Column(String(255))
    zone = Column(String(50))
    supervisor_id = Column(BigInteger, ForeignKey("supervisors.id", ondelete="NO ACTION"))
    ward_id = Column(Integer, ForeignKey("wards.id", ondelete="SET NULL"))
    collection_time = Column(String(100))
    segregation_methods = Column(JSONB)
    daily_waste_kg = Column(Numeric(10, 2))
    vendor = Column(String(255))
    remarks = Column(Text)
    consent = Column(Boolean, default=False)
    status = Column(bwg_status_enum, default="signup")
    zone_id = Column(Integer, ForeignKey("zones.id", ondelete="NO ACTION"))

    # Relationships
    supervisor = relationship("Supervisor", back_populates="bwgs")
    zone_ref = relationship("Zone", back_populates="bwgs")
    ward_ref = relationship("Ward", back_populates="bwgs")

    billing_contract = relationship(
        "BillingContract", back_populates="bwg", uselist=False
    )
    daily_aggregates = relationship(
        "BwgDailyAggregate", back_populates="bwg", cascade="all, delete-orphan"
    )
    grievances = relationship("Grievance", back_populates="bwg")
    invoices = relationship("Invoice", back_populates="bwg")
    notifications = relationship("Notification", back_populates="bwg")
    pickups = relationship("Pickup", back_populates="bwg")


class BwgDailyAggregate(Base):
    __tablename__ = "bwg_daily_aggregates"

    bwg_id = Column(String(10), ForeignKey("bwg.id", ondelete="CASCADE"), primary_key=True)
    date = Column(Date, primary_key=True)
    collected_kg = Column(Numeric(12, 2), nullable=False, default=0)
    transported_kg = Column(Numeric(12, 2), nullable=False, default=0)
    processed_kg = Column(Numeric(12, 2), nullable=False, default=0)
    disposed_kg = Column(Numeric(12, 2), nullable=False, default=0)
    total_trips = Column(Integer, nullable=False, default=0)

    bwg = relationship("Bwg", back_populates="daily_aggregates")


class DailyProcessingAnalytics(Base):
    """
    Daily processing analytics with random variations within ±25% range.
    Stores three types of data:
    - BWG Wise: Variation for specific BWGs on given date
    - Vehicle Wise: Variation for specific vehicles on given date
    - Total Processing: Variation for total daily processing
    """
    __tablename__ = "daily_processing_analytics"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    bwg_id = Column(String(10), ForeignKey("bwg.id", ondelete="CASCADE"), index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.vehicle_id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Random variation values within ±25% of the base amount
    bwg_wise_variation_percent = Column(Numeric(5, 1), nullable=True)  # ±25%
    vehicle_wise_variation_percent = Column(Numeric(5, 1), nullable=True)  # ±25%
    total_processing_variation_percent = Column(Numeric(5, 1), nullable=True)  # ±25%
    
    # Actual calculated quantities (base + variation)
    bwg_wise_quantity_kg = Column(Numeric(12, 2), nullable=True)  # Calculated quantity
    vehicle_wise_quantity_kg = Column(Numeric(12, 2), nullable=True)  # Calculated quantity
    total_processing_quantity_kg = Column(Numeric(12, 2), nullable=True)  # Calculated quantity
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    bwg = relationship("Bwg", foreign_keys=[bwg_id])


class BwgCollectionReport(Base):
    """
    Daily BWG collection report with daily waste quantities.
    One row per BWG per day with ±25% variation of daily_waste_kg.
    """
    __tablename__ = "bwg_collection_report"

    id = Column(Integer, primary_key=True)
    bwg_id = Column(String(50), nullable=True, index=True)
    bwg_name = Column(String(255), nullable=True)
    date = Column(Date, nullable=True, index=True)
    corporation = Column(String(255), nullable=True)
    ward_info = Column(String(255), nullable=True)
    wet_waste_kg = Column(Numeric(10, 2), nullable=True)
    dry_waste_kg = Column(Numeric(10, 2), nullable=True)
    vehicle_no = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=False), nullable=True, server_default=func.now())
    updated_at = Column(DateTime(timezone=False), nullable=True, server_default=func.now())


class BillingContract(Base):
    __tablename__ = "billing_contracts"

    contract_id = Column(UUID(as_uuid=True), primary_key=True)
    bwg_id = Column(String(10), ForeignKey("bwg.id", ondelete="CASCADE"), unique=True, nullable=False)
    default_amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    billing_interval = Column(billing_interval_enum, nullable=False, default="MONTHLY")
    billing_day_of_month = Column(Integer, nullable=False, default=1)
    next_invoice_date = Column(Date, nullable=False)
    status = Column(contract_status_enum, nullable=False, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    invoice_counter = Column(Integer, nullable=False, default=1000)

    bwg = relationship("Bwg", back_populates="billing_contract")
    invoices = relationship("Invoice", back_populates="contract")


class BwgSignup(Base):
    __tablename__ = "bwg_signup"

    id = Column(Integer, primary_key=True)
    email = Column(Text, nullable=False, unique=True)
    password = Column(Text, nullable=False)
    username = Column(Text)
    phone = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    has_submitted_registration = Column(Boolean, default=False)
    registration_id = Column(Integer, ForeignKey("registrations.id"))
    status = Column(Text, default="signup_only")

    registration = relationship("Registration", back_populates="bwg_signups")


# ------------------------------ Drivers & Trips ------------------------------


class Driver(Base):
    __tablename__ = "driver"

    id = Column(String(10), primary_key=True)
    username = Column(String(255), nullable=False)
    password = Column(String(255), nullable=False)
    gmail = Column(String(255), nullable=False, unique=True)
    phone_number = Column(String(15), unique=True)
    license_number = Column(String(50), nullable=False, unique=True)
    name = Column(String(255))
    ward_id = Column(Integer, ForeignKey("wards.id", ondelete="SET NULL"))

    ward = relationship("Ward", back_populates="drivers")
    live_location = relationship(
        "DriverLiveLocation", back_populates="driver", uselist=False
    )
    location_history = relationship(
        "DriverLocationHistory", back_populates="driver", cascade="all, delete-orphan"
    )
    tokens = relationship(
        "DriverToken", back_populates="driver", cascade="all, delete-orphan"
    )
    trips = relationship("Trip", back_populates="driver")
    vehicles = relationship("Vehicle", back_populates="driver")
    supervisors = relationship(
        "Supervisor",
        back_populates="driver_assigned_ref",
        foreign_keys="Supervisor.driver_assigned",
    )
    grievances_at_submission = relationship(
        "Grievance",
        back_populates="driver_at_submission",
        foreign_keys="Grievance.driver_at_submission_id",
    )


class DriverLiveLocation(Base):
    __tablename__ = "driver_live_location"

    id = Column(Integer, primary_key=True)
    driver_id = Column(String(10), ForeignKey("driver.id", ondelete="CASCADE"), unique=True, nullable=False)
    latitude = Column(Float := Numeric(precision=53))  # Using Numeric as stand-in for Double
    longitude = Column(Float)
    speed = Column(Float)
    heading = Column(Float)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    driver = relationship("Driver", back_populates="live_location")


class DriverLocationHistory(Base):
    __tablename__ = "driver_location_history"

    id = Column(BigInteger, primary_key=True)
    driver_id = Column(String(10), ForeignKey("driver.id", ondelete="CASCADE"), nullable=False)
    trip_id = Column(Integer, ForeignKey("trips.trip_id", ondelete="SET NULL"))
    latitude = Column(Float)
    longitude = Column(Float)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    driver = relationship("Driver", back_populates="location_history")
    trip = relationship("Trip", back_populates="location_history")


class DriverToken(Base):
    __tablename__ = "driver_tokens"

    id = Column(Integer, primary_key=True)
    driver_id = Column(String(10), ForeignKey("driver.id", ondelete="CASCADE"))
    token = Column(String(128), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    driver = relationship("Driver", back_populates="tokens")


class Vehicle(Base):
    __tablename__ = "vehicles"

    vehicle_id = Column(Integer, primary_key=True)
    registration_number = Column(String(20), nullable=False, unique=True)
    vehicle_type = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    driver_id = Column(String(10), ForeignKey("driver.id", ondelete="SET NULL"))
    supervisor_id = Column(Integer, ForeignKey("supervisors.id", ondelete="SET NULL"))
    ward_id = Column(Integer, ForeignKey("wards.id", ondelete="SET NULL"))
    corporation = Column(String(255))

    driver = relationship("Driver", back_populates="vehicles")
    ward = relationship("Ward", back_populates="vehicles")

    supervisor = relationship(
        "Supervisor",
        back_populates="assigned_vehicles",
        foreign_keys=[supervisor_id],
    )

    supervisors = relationship(
        "Supervisor",
        back_populates="vehicle_assigned_ref",
        foreign_keys="Supervisor.vehicle_assigned",
        viewonly=True,
    )

    trips = relationship("Trip", back_populates="vehicle")
    grievances_at_submission = relationship(
        "Grievance",
        back_populates="vehicle_at_submission",
        foreign_keys="Grievance.vehicle_at_submission_id",
    )


class Trip(Base):
    __tablename__ = "trips"

    trip_id = Column(Integer, primary_key=True)
    trip_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    vehicle_id = Column(Integer, ForeignKey("vehicles.vehicle_id", ondelete="SET NULL"))
    driver_id = Column(String(10), ForeignKey("driver.id", ondelete="SET NULL"))
    status = Column(String(20), nullable=False, default="PENDING")
    supervisor_id = Column(Integer, ForeignKey("supervisors.id"))

    vehicle = relationship("Vehicle", back_populates="trips")
    driver = relationship("Driver", back_populates="trips")
    supervisor = relationship("Supervisor", back_populates="trips")
    pickups = relationship("Pickup", back_populates="trip")
    location_history = relationship("DriverLocationHistory", back_populates="trip")


# ---------------------------- Supervisors & BWGs ----------------------------


class Supervisor(Base):
    __tablename__ = "supervisors"

    id = Column(BigInteger, primary_key=True)
    name = Column(String(255), nullable=False)
    gmail = Column(String(255), nullable=False, unique=True)
    password = Column(Text, nullable=False)
    zone = Column(String(100))
    driver_assigned = Column(String(10), ForeignKey("driver.id"))
    vehicle_assigned = Column(Integer, ForeignKey("vehicles.vehicle_id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    ward_number = Column(String(50))
    ward_name = Column(String(100))

    bwgs = relationship("Bwg", back_populates="supervisor")
    pickups = relationship("Pickup", back_populates="supervisor")
    trips = relationship("Trip", back_populates="supervisor")
    assigned_vehicles = relationship(
        "Vehicle",
        back_populates="supervisor",
        foreign_keys="Vehicle.supervisor_id",
    )
    grievances_at_submission = relationship(
        "Grievance",
        back_populates="supervisors_at_submission",
        foreign_keys="Grievance.supervisors_at_submission_id",
    )
    driver_assigned_ref = relationship(
        "Driver",
        back_populates="supervisors",
        foreign_keys=[driver_assigned],
    )
    vehicle_assigned_ref = relationship(
        "Vehicle",
        back_populates="supervisors",
        foreign_keys=[vehicle_assigned],
    )


# ---------------------------- Registrations & Pickup ----------------------------


class Registration(Base):
    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True)
    organization_name = Column(Text, nullable=False)
    generator_type = Column(Text, nullable=False)
    contact_person = Column(Text, nullable=False)
    contact_number = Column(Text, nullable=False)
    email = Column(Text)
    address = Column(Text, nullable=False)
    waste_types = Column(JSONB)
    id_proof_url = Column(Text)
    org_photo_url = Column(Text)
    status = Column(Text, default="pending")
    created_at = Column(DateTime, server_default=func.now())
    location = Column(Text)
    inspection_date = Column(DateTime)
    avg_daily_qty = Column(Text)
    existing_vendor = Column(Text)
    remarks = Column(Text)
    declaration = Column(Boolean)
    preferred_collection_time = Column(Text)
    pincode = Column(Text)
    ward = Column(Text)
    zone = Column(Text)
    zone_id = Column(Integer)
    ward_id = Column(Integer, ForeignKey("wards.id", ondelete="SET NULL"))

    ward = relationship("Ward", back_populates="registrations")
    bwg_signups = relationship("BwgSignup", back_populates="registration")


class PickupAddress(Base):
    __tablename__ = "pickup_address"

    id = Column(String(10), primary_key=True)
    organization_name = Column(Text, nullable=False)
    generator_type = Column(Text, nullable=False)
    contact_person = Column(Text, nullable=False)
    contact_number = Column(Text, nullable=False)
    email = Column(Text)
    address = Column(Text, nullable=False)
    waste_types = Column(JSONB)
    id_proof_url = Column(Text)
    org_photo_url = Column(Text)
    status = Column(Text, default="pending")
    created_at = Column(DateTime, server_default=func.now())
    location = Column(Text)
    inspection_date = Column(DateTime)
    avg_daily_qty = Column(Text)
    existing_vendor = Column(Text)
    remarks = Column(Text)
    declaration = Column(Boolean)
    preferred_collection_time = Column(Text)
    pincode = Column(Text)
    ward = Column(Text)
    zone = Column(Text)
    zone_id = Column(Integer)


class Pickup(Base):
    __tablename__ = "pickups"

    pickup_id = Column(Integer, primary_key=True)
    bwg_id = Column(String(10), ForeignKey("bwg.id", ondelete="CASCADE"), nullable=False)
    trip_id = Column(Integer, ForeignKey("trips.trip_id", ondelete="RESTRICT"), nullable=False)
    scheduled_date = Column(Date, nullable=False)
    scheduled_time_slot = Column(String(50))
    status = Column(pickup_status_enum, nullable=False, default="PENDING")
    actual_pickup_timestamp = Column(DateTime(timezone=True))
    driver_remarks = Column(Text)
    quantity_kg = Column(Numeric(12, 2))  # Calculated waste quantity for this pickup
    variation_percent = Column(Numeric(5, 1))  # Variation from daily average (e.g., +7.8, -14.2)
    is_missed = Column(Boolean, default=False)  # Was this pickup missed?
    carried_from_date = Column(Date)  # If missed, which previous date's quantity is carried forward?
    created_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at = Column(DateTime(timezone=True), server_default=func.current_timestamp())
    location = Column(String(255), nullable=False, default="https://maps.google.com")
    supervisor_id = Column(Integer, ForeignKey("supervisors.id"))

    bwg = relationship("Bwg", back_populates="pickups")
    trip = relationship("Trip", back_populates="pickups")
    supervisor = relationship("Supervisor", back_populates="pickups")


# ------------------------------ Grievances & Logs ------------------------------


class Grievance(Base):
    __tablename__ = "grievances"

    id = Column(BigInteger, primary_key=True)
    ticket_display_id = Column(String(100), unique=True)
    bwg_id = Column(String(10), ForeignKey("bwg.id"))
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(grievance_category_enum, nullable=False)
    status = Column(grievance_status_enum, nullable=False, default="Open")
    incident_at = Column(DateTime(timezone=True), nullable=False)
    ward_at_submission = Column(String(100))
    zone_at_submission = Column(String(100))
    supervisors_at_submission_id = Column(BigInteger, ForeignKey("supervisors.id"))
    vehicle_at_submission_id = Column(Integer, ForeignKey("vehicles.vehicle_id"))
    driver_at_submission_id = Column(String(10), ForeignKey("driver.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True))
    closed_at = Column(DateTime(timezone=True))

    bwg = relationship("Bwg", back_populates="grievances")
    attachments = relationship(
        "GrievanceAttachment", back_populates="grievance", cascade="all, delete-orphan"
    )
    logs = relationship(
        "GrievanceLog", back_populates="grievance", cascade="all, delete-orphan"
    )
    supervisors_at_submission = relationship(
        "Supervisor",
        back_populates="grievances_at_submission",
        foreign_keys=[supervisors_at_submission_id],
    )
    vehicle_at_submission = relationship(
        "Vehicle",
        back_populates="grievances_at_submission",
        foreign_keys=[vehicle_at_submission_id],
    )
    driver_at_submission = relationship(
        "Driver",
        back_populates="grievances_at_submission",
        foreign_keys=[driver_at_submission_id],
    )


class GrievanceAttachment(Base):
    __tablename__ = "grievance_attachments"

    id = Column(BigInteger, primary_key=True)
    grievance_id = Column(BigInteger, ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False)
    file_url = Column(Text, nullable=False)
    file_name = Column(String(255))
    file_type = Column(String(100))
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    grievance = relationship("Grievance", back_populates="attachments")


class GrievanceLog(Base):
    __tablename__ = "grievance_logs"

    id = Column(BigInteger, primary_key=True)
    grievance_id = Column(BigInteger, ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False)
    actor_id = Column(String(20))
    actor_type = Column(String(50), default="system")
    action = Column(Text, nullable=False)
    old_status = Column(grievance_status_enum)
    new_status = Column(grievance_status_enum)
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    grievance = relationship("Grievance", back_populates="logs")


# ------------------------------ Billing & Payments ------------------------------


class Invoice(Base):
    __tablename__ = "invoices"

    invoice_id = Column(UUID(as_uuid=True), primary_key=True)
    bwg_id = Column(String(10), ForeignKey("bwg.id", ondelete="SET NULL"))
    contract_id = Column(UUID(as_uuid=True), ForeignKey("billing_contracts.contract_id", ondelete="SET NULL"))
    invoice_number = Column(String(20), nullable=False, unique=True)
    description = Column(Text, nullable=False)
    amount_due = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    status = Column(invoice_status_enum, nullable=False, default="UNPAID")
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    paid_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    bwg = relationship("Bwg", back_populates="invoices")
    contract = relationship("BillingContract", back_populates="invoices")
    transactions = relationship(
        "Transaction", back_populates="invoice", cascade="all, delete-orphan"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(UUID(as_uuid=True), primary_key=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False)
    razorpay_payment_id = Column(String(255))
    razorpay_order_id = Column(String(255), nullable=False)
    razorpay_signature = Column(String(255))
    amount_paid = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    status = Column(transaction_status_enum, nullable=False)
    gateway_response = Column(JSONB)
    paid_at = Column(DateTime(timezone=True), nullable=False)

    invoice = relationship("Invoice", back_populates="transactions")


class Notification(Base):
    __tablename__ = "notifications"

    notification_id = Column(UUID(as_uuid=True), primary_key=True)
    bwg_id = Column(String(10), ForeignKey("bwg.id", ondelete="CASCADE"), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(notification_type_enum, nullable=False, default="PAYMENT")
    is_read = Column(Boolean, nullable=False, default=False)
    link = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False)

    bwg = relationship("Bwg", back_populates="notifications")
