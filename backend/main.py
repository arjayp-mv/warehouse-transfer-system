"""
Warehouse Transfer Planning Tool - FastAPI Application
Main application entry point with API routing and middleware setup
"""

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
import uvicorn
from pathlib import Path
import pymysql
import io
from datetime import datetime
from typing import Optional
import logging
import uuid
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)

# Import our modules
try:
    from . import database
    from . import models
    from . import calculations
    from . import import_export
    from . import settings
    from . import supplier_matcher
    from .cache_manager import create_cache_manager
    try:
        from .database_pool import get_connection_pool
        database.get_connection_pool = get_connection_pool
    except ImportError:
        pass
except ImportError:
    # For direct execution - add current directory to path
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import database
    import models
    import calculations
    import import_export
    import settings
    import supplier_matcher
    from cache_manager import create_cache_manager
    try:
        from database_pool import get_connection_pool
        database.get_connection_pool = get_connection_pool
    except ImportError:
        pass

# Create FastAPI application
app = FastAPI(
    title="Warehouse Transfer Planning Tool",
    description="Intelligent inventory transfer recommendations with stockout correction",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Add CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Disable static file caching in development mode
is_development = os.getenv("DEBUG") == "true" or os.getenv("ENVIRONMENT") == "development"
if is_development:
    # Monkey patch to disable caching for development
    StaticFiles.is_not_modified = lambda self, *args, **kwargs: False

# Mount static files for frontend
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

# Setup Sales Analytics API Routes (separate from transfer planning)
try:
    from backend.sales_api import setup_sales_routes
    setup_sales_routes(app)
    logger.info("Sales analytics routes loaded successfully")
except ImportError as e:
    logger.warning(f"Sales analytics module not available: {e}")
except Exception as e:
    logger.error(f"Error setting up sales routes: {e}")

# Setup Forecasting API Routes (12-month sales forecasting)
try:
    from backend.forecasting_api import router as forecasting_router
    app.include_router(forecasting_router)
    logger.info("Forecasting API routes loaded successfully")
except ImportError as e:
    logger.warning(f"Forecasting module not available: {e}")
except Exception as e:
    logger.error(f"Error setting up forecasting routes: {e}")

# Setup Supplier Ordering API Routes (V9.0 monthly ordering system)
try:
    from backend.supplier_ordering_api import router as supplier_ordering_router
    app.include_router(supplier_ordering_router)
    logger.info("Supplier ordering API routes loaded successfully")
except ImportError as e:
    logger.warning(f"Supplier ordering module not available: {e}")
except Exception as e:
    logger.error(f"Error setting up supplier ordering routes: {e}")

# Setup Supplier Management API Routes (supplier lead time management)
try:
    from backend.supplier_management_api import router as supplier_management_router
    app.include_router(supplier_management_router)
    logger.info("Supplier management API routes loaded successfully")
except ImportError as e:
    logger.warning(f"Supplier management module not available: {e}")
except Exception as e:
    logger.error(f"Error setting up supplier management routes: {e}")

# Setup Supplier Ordering SKU Details API Routes (V10.0 SKU detail endpoints)
try:
    from backend.supplier_ordering_sku_details import router as sku_details_router
    app.include_router(sku_details_router)
    logger.info("Supplier ordering SKU details API routes loaded successfully")
except ImportError as e:
    logger.warning(f"Supplier ordering SKU details module not available: {e}")
except Exception as e:
    logger.error(f"Error setting up supplier ordering SKU details routes: {e}")

# =============================================================================
# API ENDPOINTS - WAREHOUSE TRANSFER PLANNING TOOL
# =============================================================================
# Purpose: RESTful API for inventory management and transfer recommendations
# Architecture: FastAPI with automatic OpenAPI documentation generation
# Performance: Optimized queries with database connection pooling
# Security: CORS enabled, input validation, error handling
# Business Logic: Stockout correction, ABC-XYZ classification, transfer calculations

@app.get("/", 
         summary="Application Root", 
         description="Basic application information and health status",
         tags=["System"])
async def root():
    """Root endpoint serving the dashboard"""
    return {"message": "Warehouse Transfer Planning Tool", "version": "1.0.0", "status": "running"}

@app.get("/health",
         summary="System Health Check", 
         description="Verify database connectivity and system status",
         tags=["System"],
         responses={
             200: {"description": "System is healthy and database is connected"},
             500: {"description": "Database connection failed or system error"}
         })
async def health_check():
    """
    Comprehensive system health check endpoint
    
    Verifies:
    - Database connectivity and query execution
    - System components availability
    - Application version information
    
    Returns:
        dict: System status with database connection status and version info
    
    Raises:
        HTTPException: 500 error if database connection fails
        
    Business Use:
    - Monitoring and alerting systems
    - Load balancer health checks  
    - Deployment verification
    """
    try:
        # Test database connection with simple query
        db = database.get_database_connection()
        cursor = db.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        db.close()
        
        return {
            "status": "healthy",
            "database": "connected", 
            "version": "1.0.0",
            "components": {
                "api": "operational",
                "database": "connected",
                "calculations": "ready"
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"System health check failed: {str(e)}"
        )

# =============================================================================
# CORE API ENDPOINTS - INVENTORY & TRANSFER MANAGEMENT
# =============================================================================

@app.get("/api/skus",
         summary="Get All Active SKUs",
         description="Retrieve all active SKUs with current inventory levels and stock status",
         tags=["Inventory Management"],
         responses={
             200: {
                 "description": "List of active SKUs with inventory data",
                 "content": {
                     "application/json": {
                         "example": {
                             "skus": [
                                 {
                                     "sku_id": "CHG-001",
                                     "description": "USB-C Fast Charger 65W",
                                     "supplier": "Supplier A",
                                     "abc_code": "A",
                                     "xyz_code": "X", 
                                     "transfer_multiple": 25,
                                     "burnaby_qty": 500,
                                     "kentucky_qty": 0,
                                     "stock_status": "OUT_OF_STOCK"
                                 }
                             ],
                             "count": 4
                         }
                     }
                 }
             },
             500: {"description": "Database query failed"}
         })
async def get_skus():
    """
    Retrieve all active SKUs with comprehensive inventory information
    
    Business Logic:
    - Joins SKU master data with current inventory levels
    - Calculates stock status based on Kentucky warehouse quantities
    - Sorts by urgency (out of stock first) then by SKU ID
    - Only includes active SKUs (excludes Death Row/Discontinued)
    
    Stock Status Logic:
    - OUT_OF_STOCK: Kentucky qty = 0 (critical)
    - LOW_STOCK: Kentucky qty < 100 (warning)  
    - IN_STOCK: Kentucky qty >= 100 (normal)
    
    Returns:
        dict: List of SKUs with inventory data and total count
        
    Raises:
        HTTPException: 500 error if database query fails
        
    Usage:
        Used by dashboard for total SKU count
        Used by frontend for detailed SKU browsing
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        
        # Comprehensive SKU query with inventory status calculation - shows all SKUs
        query = """
        SELECT
            s.sku_id,
            s.description,
            s.supplier,
            s.status,
            s.cost_per_unit,
            s.abc_code,
            s.xyz_code,
            s.transfer_multiple,
            COALESCE(ic.burnaby_qty, 0) as burnaby_qty,
            COALESCE(ic.kentucky_qty, 0) as kentucky_qty,
            CASE
                WHEN COALESCE(ic.kentucky_qty, 0) = 0 THEN 'OUT_OF_STOCK'
                WHEN COALESCE(ic.kentucky_qty, 0) < 100 THEN 'LOW_STOCK'
                ELSE 'IN_STOCK'
            END as stock_status
        FROM skus s
        LEFT JOIN inventory_current ic ON s.sku_id = ic.sku_id
        ORDER BY
            COALESCE(ic.kentucky_qty, 0) ASC,  -- Out of stock first
            s.sku_id
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        db.close()
        
        return {"skus": results, "count": len(results)}

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"SKU query failed: {str(e)}"
        )

@app.get("/api/skus/count",
         summary="Get SKU Count",
         description="Get the total count of active SKUs in the system",
         tags=["Inventory Management"],
         responses={
             200: {
                 "description": "SKU count information",
                 "content": {
                     "application/json": {
                         "example": {
                             "count": 4127,
                             "active": 4100,
                             "death_row": 25,
                             "discontinued": 2
                         }
                     }
                 }
             },
             500: {"description": "Database query failed"}
         })
async def get_sku_count():
    """
    Get comprehensive SKU count statistics

    Returns total counts by status and provides accurate statistics
    for dashboard display and data integrity checks.

    Returns:
        dict: SKU count statistics including totals by status
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        # Get counts by status
        query = """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'Active' THEN 1 ELSE 0 END) as active,
            SUM(CASE WHEN status = 'Death Row' THEN 1 ELSE 0 END) as death_row,
            SUM(CASE WHEN status = 'Discontinued' THEN 1 ELSE 0 END) as discontinued
        FROM skus
        """

        cursor.execute(query)
        result = cursor.fetchone()
        db.close()

        return {
            "count": result['total'],
            "active": result['active'],
            "death_row": result['death_row'],
            "discontinued": result['discontinued']
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"SKU count query failed: {str(e)}"
        )


@app.get("/api/dashboard",
         summary="Get Dashboard Metrics",
         description="Retrieve key business metrics and alerts for the main dashboard",
         tags=["Dashboard"],
         responses={
             200: {
                 "description": "Dashboard metrics with KPIs and system alerts",
                 "content": {
                     "application/json": {
                         "example": {
                             "metrics": {
                                 "out_of_stock": 1,
                                 "low_stock": 1, 
                                 "total_inventory_value": 26250.00,
                                 "current_month_sales": 540,
                                 "stockout_affected_skus": 1
                             },
                             "alerts": [
                                 {"type": "danger", "message": "1 SKUs are out of stock"},
                                 {"type": "warning", "message": "1 SKUs have low stock"}
                             ],
                             "timestamp": "2024-03-15T10:00:00Z"
                         }
                     }
                 }
             },
             500: {"description": "Dashboard query failed"}
         })
async def get_dashboard_metrics():
    """
    Generate comprehensive dashboard metrics for business intelligence
    
    Key Performance Indicators (KPIs):
    - Out of stock count: Critical inventory shortages requiring immediate action
    - Low stock count: Items below safety threshold needing attention  
    - Total inventory value: Current dollar value of Kentucky warehouse inventory
    - Current month sales: Units sold in current month across all SKUs
    - Stockout affected SKUs: Items that experienced stockouts this month
    
    Alert Generation:
    - Creates actionable alerts based on current inventory status
    - Filters out null alerts for clean presentation
    - Uses color coding (danger/warning/info) for visual priority
    
    Business Impact:
    - Enables data-driven inventory decisions
    - Provides early warning system for stock issues
    - Tracks monthly performance trends
    
    Returns:
        dict: Comprehensive dashboard data with metrics, alerts, and timestamp
        
    Raises:
        HTTPException: 500 error if any database query fails
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        
        # Out of stock count
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM inventory_current 
            WHERE kentucky_qty = 0
        """)
        out_of_stock = cursor.fetchone()['count']
        
        # Low stock count (< 100 units)
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM inventory_current 
            WHERE kentucky_qty > 0 AND kentucky_qty < 100
        """)
        low_stock = cursor.fetchone()['count']
        
        # Total inventory value (Kentucky)
        cursor.execute("""
            SELECT SUM(ic.kentucky_qty * s.cost_per_unit) as value
            FROM inventory_current ic
            JOIN skus s ON ic.sku_id = s.sku_id
            WHERE s.status = 'Active'
        """)
        result = cursor.fetchone()
        total_value = float(result['value']) if result['value'] else 0
        
        # Get current month in YYYY-MM format
        from datetime import datetime
        current_month = datetime.now().strftime('%Y-%m')

        # Recent sales (current month) - both quantity and revenue
        cursor.execute("""
            SELECT
                SUM(kentucky_sales + burnaby_sales) as total_sales,
                SUM(kentucky_revenue + burnaby_revenue) as total_revenue,
                SUM(kentucky_revenue) as kentucky_revenue,
                SUM(burnaby_revenue) as burnaby_revenue
            FROM monthly_sales
            WHERE `year_month` = %s
        """, (current_month,))
        result = cursor.fetchone()
        current_sales = result['total_sales'] if result['total_sales'] else 0
        revenue_mtd = float(result['total_revenue']) if result['total_revenue'] else 0
        kentucky_revenue_mtd = float(result['kentucky_revenue']) if result['kentucky_revenue'] else 0
        burnaby_revenue_mtd = float(result['burnaby_revenue']) if result['burnaby_revenue'] else 0

        # Calculate average revenue per unit for current month
        avg_revenue_per_unit = round(float(revenue_mtd) / float(current_sales), 2) if current_sales > 0 else 0

        # Previous month revenue for comparison
        import datetime as dt
        prev_month = (datetime.now().replace(day=1) - dt.timedelta(days=1)).strftime('%Y-%m')
        cursor.execute("""
            SELECT SUM(kentucky_revenue + burnaby_revenue) as prev_revenue
            FROM monthly_sales
            WHERE `year_month` = %s
        """, (prev_month,))
        result = cursor.fetchone()
        revenue_prev_month = float(result['prev_revenue']) if result['prev_revenue'] else 0

        # Year to date revenue
        current_year = datetime.now().strftime('%Y')
        cursor.execute("""
            SELECT SUM(kentucky_revenue + burnaby_revenue) as ytd_revenue
            FROM monthly_sales
            WHERE `year_month` LIKE %s
        """, (f"{current_year}-%",))
        result = cursor.fetchone()
        revenue_ytd = float(result['ytd_revenue']) if result['ytd_revenue'] else 0

        # SKUs with stockouts this month
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM monthly_sales
            WHERE `year_month` = %s AND kentucky_stockout_days > 0
        """, (current_month,))
        stockout_skus = cursor.fetchone()['count']
        
        db.close()
        
        return {
            "metrics": {
                "out_of_stock": out_of_stock,
                "low_stock": low_stock,
                "total_inventory_value": round(total_value, 2),
                "current_month_sales": current_sales,
                "stockout_affected_skus": stockout_skus,
                # Revenue metrics
                "revenue_mtd": round(revenue_mtd, 2),
                "burnaby_revenue_mtd": round(burnaby_revenue_mtd, 2),
                "kentucky_revenue_mtd": round(kentucky_revenue_mtd, 2),
                "avg_revenue_per_unit_mtd": avg_revenue_per_unit,
                "revenue_prev_month": round(revenue_prev_month, 2),
                "revenue_ytd": round(revenue_ytd, 2)
            },
            "alerts": [
                {"type": "danger", "message": f"{out_of_stock} SKUs are out of stock"} if out_of_stock > 0 else None,
                {"type": "warning", "message": f"{low_stock} SKUs have low stock"} if low_stock > 0 else None,
                {"type": "info", "message": f"{stockout_skus} SKUs affected by stockouts this month"} if stockout_skus > 0 else None
            ],
            "timestamp": "2024-03-15T10:00:00Z"  # In production, use actual timestamp
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dashboard query failed: {str(e)}")

# Test POST endpoint to debug endpoint registration issue
@app.post("/api/debug-test", 
          summary="Debug Test Endpoint",
          description="Test endpoint to debug endpoint registration issues")
async def debug_test():
    return {"message": "Debug test endpoint working", "method": "POST"}

@app.get("/api/transfer-recommendations",
         summary="Generate Transfer Recommendations", 
         description="Calculate optimal inventory transfer quantities using stockout-corrected demand",
         tags=["Transfer Planning"],
         responses={
             200: {
                 "description": "List of transfer recommendations with priorities and reasoning",
                 "content": {
                     "application/json": {
                         "example": {
                             "recommendations": [
                                 {
                                     "sku_id": "CHG-001",
                                     "description": "USB-C Fast Charger 65W",
                                     "current_kentucky_qty": 0,
                                     "current_burnaby_qty": 500,
                                     "corrected_monthly_demand": 0.0,
                                     "recommended_transfer_qty": 0,
                                     "coverage_months": 0.0,
                                     "target_coverage_months": 4,
                                     "priority": "CRITICAL",
                                     "reason": "Stockout correction applied (25 days out); Currently out of stock",
                                     "abc_class": "A",
                                     "xyz_class": "X",
                                     "transfer_multiple": 25,
                                     "stockout_days": 25
                                 }
                             ],
                             "count": 4,
                             "generated_at": "2024-03-15T10:00:00Z"
                         }
                     }
                 }
             },
             500: {"description": "Transfer calculation failed"}
         })
async def get_transfer_recommendations(
    priority_first: bool = False,
    page: int = 1,
    page_size: int = 100
):
    """
    Generate intelligent transfer recommendations using advanced inventory algorithms
    
    Core Business Logic:
    1. Stockout Correction: Adjusts demand based on availability rate with 30% floor
    2. ABC-XYZ Classification: Determines target coverage based on value and variability  
    3. Priority Scoring: CRITICAL (out of stock) > HIGH (< 1 month) > MEDIUM/LOW
    4. Transfer Optimization: Rounds to multiples, respects minimums, checks availability
    
    Algorithm Details:
    - Uses monthly sales data with stockout days count (simplified approach)
    - Applies corrected_demand = monthly_sales / max(availability_rate, 0.3)
    - Calculates target_inventory = corrected_demand × coverage_months
    - Determines transfer_need = target_inventory - current_position
    - Rounds to appropriate multiples (25/50/100) with 10-unit minimum
    
    Priority Logic:
    - CRITICAL: Kentucky qty = 0 (immediate action required)
    - HIGH: Coverage < 1 month (urgent restocking needed)  
    - MEDIUM: Coverage < 2 months (planned restocking)
    - LOW: Adequate coverage (maintenance transfers)
    
    Business Impact:
    - Prevents stockouts through predictive analytics
    - Optimizes cash flow by right-sizing transfers
    - Reduces manual calculation time from hours to seconds
    - Provides audit trail with detailed reasoning
    
    Returns:
        dict: Complete transfer recommendations with metadata
        
    Raises:
        HTTPException: 500 error if calculation engine fails
        
    Usage:
        Primary endpoint for transfer planning interface
        Data exported to Excel for warehouse execution
    """
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("DEBUG: transfer-recommendations endpoint called")

        # Generate all recommendations using sophisticated calculation engine
        all_recommendations = calculations.calculate_all_transfer_recommendations()
        logger.error(f"DEBUG: Got {len(all_recommendations)} total recommendations")

        # Apply priority sorting if requested
        if priority_first:
            # Sort by priority (red > yellow > green), then by urgency score
            priority_map = {"red": 3, "yellow": 2, "green": 1, "": 0}
            all_recommendations.sort(
                key=lambda x: (
                    priority_map.get(x.get("priority_level", ""), 0),
                    x.get("urgency_score", 0)
                ),
                reverse=True
            )

        # Calculate pagination
        total_count = len(all_recommendations)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_recommendations = all_recommendations[start_idx:end_idx]

        # Calculate pagination metadata
        total_pages = (total_count + page_size - 1) // page_size
        has_next = page < total_pages
        has_prev = page > 1

        return {
            "recommendations": page_recommendations,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev
            },
            "generated_at": "2024-03-15T10:00:00Z",
            "algorithm_version": "1.0-monthly-stockout-correction",
            "business_rules": {
                "min_transfer_qty": 10,
                "stockout_correction_floor": 0.3,
                "max_correction_multiplier": 1.5,
                "coverage_targets": {
                    "AX": 4, "AY": 5, "AZ": 6,
                    "BX": 3, "BY": 4, "BZ": 5,
                    "CX": 2, "CY": 2, "CZ": 1
                }
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Transfer calculation engine failed: {str(e)}"
        )

@app.get("/api/sku/{sku_id}")
async def get_sku_details(sku_id: str):
    """Get detailed information for a specific SKU"""
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        
        # SKU basic info
        cursor.execute("""
            SELECT s.*, ic.burnaby_qty, ic.kentucky_qty, ic.last_updated
            FROM skus s
            LEFT JOIN inventory_current ic ON s.sku_id = ic.sku_id
            WHERE s.sku_id = %s
        """, (sku_id,))
        
        sku = cursor.fetchone()
        if not sku:
            raise HTTPException(status_code=404, detail="SKU not found")
        
        # Sales history with both warehouse corrected demands
        cursor.execute("""
            SELECT `year_month`, burnaby_sales, kentucky_sales,
                   burnaby_stockout_days, kentucky_stockout_days,
                   corrected_demand_kentucky, corrected_demand_burnaby
            FROM monthly_sales
            WHERE sku_id = %s
            ORDER BY `year_month` DESC
        """, (sku_id,))
        
        sales_history = cursor.fetchall()
        
        # Pending inventory
        cursor.execute("""
            SELECT quantity, destination, order_date, expected_arrival, status
            FROM pending_inventory
            WHERE sku_id = %s AND status IN ('ordered', 'shipped')
        """, (sku_id,))
        
        pending = cursor.fetchall()

        db.close()

        return {
            "sku": sku,
            "sales_history": sales_history,
            "pending_inventory": pending
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@app.get("/api/test-weighted-demand/{sku_id}",
         summary="Test Weighted Demand Calculations",
         description="Compare traditional single-month vs new weighted moving average demand calculations",
         tags=["Analytics"],
         responses={
             200: {
                 "description": "Comparison of demand calculation methods",
                 "content": {
                     "application/json": {
                         "example": {
                             "sku_id": "SKU123",
                             "traditional_calculation": {"corrected_demand": 150, "method": "single_month"},
                             "weighted_calculation": {
                                 "enhanced_demand": 135,
                                 "method": "weighted_3mo_avg",
                                 "demand_3mo_weighted": 135.5,
                                 "demand_6mo_weighted": 142.3,
                                 "volatility_class": "medium",
                                 "coefficient_variation": 0.45,
                                 "recommendation_basis": "3-month weighted average for BY classification"
                             },
                             "comparison": {"difference_percentage": -10.0, "method_preference": "weighted_average"}
                         }
                     }
                 }
             },
             404: {"description": "SKU not found or no sales data available"}
         })
async def test_weighted_demand_calculation(sku_id: str):
    """
    Test endpoint to compare traditional single-month demand calculation
    with new weighted moving average approach

    This endpoint helps validate that the new weighted demand calculations
    are working correctly by showing side-by-side comparison with the
    traditional approach.

    Args:
        sku_id: The SKU identifier to analyze

    Returns:
        dict: Comparison of both calculation methods with detailed metrics

    Raises:
        HTTPException: 404 if SKU not found, 500 if calculation error

    Business Use:
    - Validate new weighted average implementation
    - Compare calculation approaches during transition period
    - Troubleshoot demand calculation discrepancies
    - Performance testing of new algorithms
    """
    try:
        # Initialize calculators
        calc = calculations.TransferCalculator()

        # Get SKU information and sales data
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        # Get SKU details including ABC-XYZ classification
        cursor.execute("""
            SELECT s.sku_id, s.description, s.abc_code, s.xyz_code,
                   ic.kentucky_qty, ic.burnaby_qty
            FROM skus s
            LEFT JOIN inventory_current ic ON s.sku_id = ic.sku_id
            WHERE s.sku_id = %s AND s.status = 'Active'
        """, (sku_id,))

        sku_info = cursor.fetchone()
        if not sku_info:
            db.close()
            raise HTTPException(status_code=404, detail=f"SKU {sku_id} not found or inactive")

        # Get latest sales data for traditional calculation
        cursor.execute("""
            SELECT kentucky_sales, kentucky_stockout_days, corrected_demand_kentucky
            FROM monthly_sales
            WHERE sku_id = %s
            ORDER BY `year_month` DESC
            LIMIT 1
        """, (sku_id,))

        latest_sales = cursor.fetchone()
        db.close()

        if not latest_sales:
            raise HTTPException(status_code=404, detail=f"No sales data found for SKU {sku_id}")

        # Traditional single-month calculation (existing logic)
        kentucky_sales = latest_sales['kentucky_sales'] or 0
        stockout_days = latest_sales['kentucky_stockout_days'] or 0

        # Simple stockout correction (mimicking existing logic)
        if stockout_days > 0 and kentucky_sales > 0:
            availability_rate = max((30 - stockout_days) / 30, 0.3)
            traditional_corrected = kentucky_sales / availability_rate
            traditional_corrected = min(traditional_corrected, kentucky_sales * 1.5)
        else:
            traditional_corrected = kentucky_sales

        traditional_calculation = {
            "corrected_demand": round(traditional_corrected, 2),
            "method": "single_month",
            "raw_sales": kentucky_sales,
            "stockout_days": stockout_days,
            "availability_rate": round((30 - stockout_days) / 30, 3) if stockout_days > 0 else 1.0
        }

        # New weighted calculation
        abc_class = sku_info['abc_code'] or 'B'
        xyz_class = sku_info['xyz_code'] or 'Y'

        # Test Kentucky weighted calculation
        kentucky_weighted_result = calc.weighted_demand_calculator.get_enhanced_demand_calculation(
            sku_id, abc_class, xyz_class, kentucky_sales, stockout_days, warehouse='kentucky'
        )

        # Test Burnaby weighted calculation to verify warehouse-specific results
        burnaby_weighted_result = calc.weighted_demand_calculator.get_enhanced_demand_calculation(
            sku_id, abc_class, xyz_class, kentucky_sales, stockout_days, warehouse='burnaby'
        )

        # Calculate percentage difference for Kentucky
        traditional_demand = traditional_corrected
        kentucky_weighted_demand = kentucky_weighted_result['enhanced_demand']
        burnaby_weighted_demand = burnaby_weighted_result['enhanced_demand']

        if traditional_demand > 0:
            ky_difference_pct = round(((kentucky_weighted_demand - traditional_demand) / traditional_demand) * 100, 2)
        else:
            ky_difference_pct = 0

        # Determine method preference based on data quality
        sample_size = kentucky_weighted_result.get('sample_size_months', 0)
        data_quality = kentucky_weighted_result.get('data_quality_score', 0.0)

        if sample_size >= 3 and data_quality >= 0.7:
            method_preference = "weighted_average"
            preference_reason = "Sufficient historical data with good quality"
        elif sample_size >= 2:
            method_preference = "weighted_average"
            preference_reason = "Limited but usable historical data"
        else:
            method_preference = "single_month"
            preference_reason = "Insufficient historical data for weighted calculation"

        return {
            "sku_id": sku_id,
            "sku_info": {
                "description": sku_info['description'],
                "abc_code": abc_class,
                "xyz_code": xyz_class,
                "kentucky_qty": sku_info['kentucky_qty'] or 0,
                "burnaby_qty": sku_info['burnaby_qty'] or 0
            },
            "traditional_calculation": traditional_calculation,
            "kentucky_weighted_calculation": kentucky_weighted_result,
            "burnaby_weighted_calculation": burnaby_weighted_result,
            "warehouse_comparison": {
                "kentucky_demand": kentucky_weighted_demand,
                "burnaby_demand": burnaby_weighted_demand,
                "different_values": kentucky_weighted_demand != burnaby_weighted_demand,
                "warehouse_specific": "Calculations use warehouse-specific sales data"
            },
            "comparison": {
                "difference_percentage": ky_difference_pct,
                "method_preference": method_preference,
                "preference_reason": preference_reason,
                "improvement_notes": [
                    "Weighted average reduces single-month volatility impact",
                    "ABC-XYZ classification optimizes calculation strategy",
                    "Warehouse-specific calculations ensure accurate demand per location",
                    "Volatility metrics help identify forecast reliability"
                ]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Calculation test failed: {str(e)}")

@app.get("/api/export/sales-history/{sku_id}",
         summary="Export Individual SKU Sales History",
         description="Export comprehensive sales history for a specific SKU as CSV",
         tags=["Import/Export"],
         responses={
             200: {
                 "description": "CSV file with sales history data",
                 "content": {"text/csv": {"example": "Month,Kentucky Sales,Canada Sales,Total Sales,Stockout Days,Corrected Demand\\n2024-01,150,200,350,0,350"}}
             },
             404: {"description": "SKU not found"}
         })
async def export_sku_sales_history(sku_id: str):
    """
    Export detailed sales history for a specific SKU including:
    - Monthly sales data for both warehouses
    - Total sales calculation
    - Stockout days information
    - Corrected demand calculations

    Args:
        sku_id: The SKU identifier to export

    Returns:
        CSV file with comprehensive sales history

    Raises:
        HTTPException: 404 if SKU not found, 500 for processing errors
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        # Verify SKU exists
        cursor.execute("SELECT sku_id, description FROM skus WHERE sku_id = %s", (sku_id,))
        sku_info = cursor.fetchone()
        if not sku_info:
            db.close()
            raise HTTPException(status_code=404, detail=f"SKU '{sku_id}' not found")

        # Get sales history with all data
        cursor.execute("""
            SELECT
                `year_month`,
                burnaby_sales,
                kentucky_sales,
                (burnaby_sales + kentucky_sales) as total_sales,
                burnaby_stockout_days,
                kentucky_stockout_days,
                corrected_demand_kentucky
            FROM monthly_sales
            WHERE sku_id = %s
            ORDER BY `year_month` DESC
        """, (sku_id,))

        sales_data = cursor.fetchall()
        db.close()

        # Generate CSV content with proper formatting
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output, lineterminator='\n', quoting=csv.QUOTE_MINIMAL)

        # Write header
        writer.writerow([
            'Month', 'Kentucky Sales', 'Canada Sales', 'Total Sales',
            'Kentucky Stockout Days', 'Canada Stockout Days', 'Corrected Demand'
        ])

        # Write data rows
        for row in sales_data:
            writer.writerow([
                str(row['year_month'] or ''),
                str(row['kentucky_sales'] or 0),
                str(row['burnaby_sales'] or 0),
                str(row['total_sales'] or 0),
                str(row['kentucky_stockout_days'] or 0),
                str(row['burnaby_stockout_days'] or 0),
                str(row['corrected_demand_kentucky'] or '')
            ])

        csv_content = output.getvalue()

        # Create response with proper headers
        from fastapi.responses import Response
        filename = f"sales-history-{sku_id}-{datetime.now().strftime('%Y%m%d')}.csv"

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"SKU export error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to export SKU sales history: {str(e)}")

@app.get("/api/export/all-sales-history",
         summary="Export All SKUs Sales History",
         description="Export sales history for all SKUs with configurable column selection",
         tags=["Import/Export"],
         responses={
             200: {
                 "description": "CSV file with all SKUs sales history",
                 "content": {"text/csv": {"example": "SKU,Description,Month,Total Sales,Kentucky Sales,Canada Sales,Stockout Days"}}
             }
         })
async def export_all_sales_history(columns: str = "total,kentucky,canada,stockout"):
    """
    Export comprehensive sales history for all SKUs with flexible column selection.

    Args:
        columns: Comma-separated list of column types to include:
                - total: Total sales (CA + US combined)
                - kentucky: Kentucky/US sales only
                - canada: Canada/Burnaby sales only
                - stockout: Stockout days and corrected demand

    Returns:
        CSV file with selected columns for all SKUs

    Raises:
        HTTPException: 400 for invalid parameters, 500 for processing errors
    """
    try:
        # Parse and validate column selection
        selected_columns = [col.strip().lower() for col in columns.split(',')]
        valid_columns = {'total', 'kentucky', 'canada', 'stockout'}

        if not selected_columns or not all(col in valid_columns for col in selected_columns):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid columns. Must be comma-separated list from: {', '.join(valid_columns)}"
            )

        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        # Get all SKUs with sales data
        cursor.execute("""
            SELECT DISTINCT
                s.sku_id,
                s.description,
                ms.`year_month`,
                ms.burnaby_sales,
                ms.kentucky_sales,
                (ms.burnaby_sales + ms.kentucky_sales) as total_sales,
                ms.burnaby_stockout_days,
                ms.kentucky_stockout_days,
                ms.corrected_demand_kentucky
            FROM skus s
            INNER JOIN monthly_sales ms ON s.sku_id = ms.sku_id
            WHERE s.status = 'Active'
            ORDER BY s.sku_id, ms.`year_month` DESC
        """)

        all_sales_data = cursor.fetchall()
        db.close()

        if not all_sales_data:
            raise HTTPException(status_code=404, detail="No sales data found")

        # Build CSV headers based on selected columns
        headers = ['SKU', 'Description', 'Month']

        if 'total' in selected_columns:
            headers.append('Total Sales')
        if 'kentucky' in selected_columns:
            headers.append('Kentucky Sales')
        if 'canada' in selected_columns:
            headers.append('Canada Sales')
        if 'stockout' in selected_columns:
            headers.extend(['Kentucky Stockout Days', 'Canada Stockout Days', 'Corrected Demand'])

        # Generate CSV content with proper formatting
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output, lineterminator='\n', quoting=csv.QUOTE_MINIMAL)

        # Write header
        writer.writerow(headers)

        # Write data rows
        for row in all_sales_data:
            line_data = [
                str(row["sku_id"] or ''),
                str(row["description"] or ''),
                str(row['year_month'] or '')
            ]

            if 'total' in selected_columns:
                line_data.append(str(row['total_sales'] or 0))
            if 'kentucky' in selected_columns:
                line_data.append(str(row['kentucky_sales'] or 0))
            if 'canada' in selected_columns:
                line_data.append(str(row['burnaby_sales'] or 0))
            if 'stockout' in selected_columns:
                line_data.extend([
                    str(row['kentucky_stockout_days'] or 0),
                    str(row['burnaby_stockout_days'] or 0),
                    str(row['corrected_demand_kentucky'] or '')
                ])

            writer.writerow(line_data)

        csv_content = output.getvalue()

        # Create response with proper headers
        from fastapi.responses import Response
        column_suffix = '-'.join(selected_columns)
        filename = f"all-sales-history-{column_suffix}-{datetime.now().strftime('%Y%m%d')}.csv"

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Bulk export error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to export all sales history: {str(e)}")

@app.put("/api/skus/{sku_id}",
         summary="Update SKU Master Data",
         description="Update editable fields of an existing SKU with comprehensive validation",
         tags=["SKU Management"],
         responses={
             200: {
                 "description": "SKU updated successfully",
                 "content": {
                     "application/json": {
                         "example": {
                             "success": True,
                             "sku_id": "CHG-001",
                             "message": "SKU updated successfully",
                             "updated_fields": ["description", "cost_per_unit", "abc_code"],
                             "updated_at": "2025-09-13T10:30:00Z"
                         }
                     }
                 }
             },
             400: {"description": "Invalid input data or validation failed"},
             404: {"description": "SKU not found"},
             500: {"description": "Update operation failed"}
         })
async def update_sku(sku_id: str, update_data: models.SKUUpdateRequest):
    """
    Update SKU master data with comprehensive validation and data integrity checks

    Updates only the provided fields, leaving others unchanged.
    All updates are performed within a database transaction for data integrity.

    Args:
        sku_id: The unique SKU identifier to update
        update_data: JSON object containing the fields to update

    Updateable Fields:
        - description: Product description (1-255 characters)
        - supplier: Supplier name (max 100 characters)
        - cost_per_unit: Unit cost (0.01-99999.99, rounded to 2 decimals)
        - status: Product status (Active, Death Row, or Discontinued)
        - transfer_multiple: Transfer quantity multiple (1-9999)
        - abc_code: ABC classification (A, B, or C)
        - xyz_code: XYZ classification (X, Y, or Z)
        - category: Product category (max 50 characters)

    Returns:
        JSON object with update confirmation and details

    Raises:
        HTTPException: 400 for validation errors, 404 if SKU not found, 500 for database errors
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        # First, verify the SKU exists
        cursor.execute("SELECT sku_id FROM skus WHERE sku_id = %s", (sku_id,))
        existing_sku = cursor.fetchone()

        if not existing_sku:
            db.close()
            raise HTTPException(status_code=404, detail=f"SKU '{sku_id}' not found")

        # Build dynamic update query from provided fields
        update_fields = []
        update_values = []
        updated_field_names = []

        # Only update fields that are provided in the request
        if update_data.description is not None:
            update_fields.append("description = %s")
            update_values.append(update_data.description)
            updated_field_names.append("description")

        if update_data.supplier is not None:
            update_fields.append("supplier = %s")
            update_values.append(update_data.supplier)
            updated_field_names.append("supplier")

        if update_data.cost_per_unit is not None:
            update_fields.append("cost_per_unit = %s")
            update_values.append(update_data.cost_per_unit)
            updated_field_names.append("cost_per_unit")

        if update_data.status is not None:
            update_fields.append("status = %s")
            update_values.append(update_data.status)
            updated_field_names.append("status")

        if update_data.transfer_multiple is not None:
            update_fields.append("transfer_multiple = %s")
            update_values.append(update_data.transfer_multiple)
            updated_field_names.append("transfer_multiple")

        if update_data.abc_code is not None:
            update_fields.append("abc_code = %s")
            update_values.append(update_data.abc_code)
            updated_field_names.append("abc_code")

        if update_data.xyz_code is not None:
            update_fields.append("xyz_code = %s")
            update_values.append(update_data.xyz_code)
            updated_field_names.append("xyz_code")

        if update_data.category is not None:
            update_fields.append("category = %s")
            update_values.append(update_data.category)
            updated_field_names.append("category")

        # Check if any fields were provided for update
        if not update_fields:
            db.close()
            raise HTTPException(status_code=400, detail="No valid fields provided for update")

        # Add updated_at timestamp
        update_fields.append("updated_at = NOW()")

        # Execute the update within a transaction
        try:
            # Start transaction
            cursor.execute("START TRANSACTION")

            # Build and execute update query
            update_query = f"UPDATE skus SET {', '.join(update_fields)} WHERE sku_id = %s"
            update_values.append(sku_id)

            cursor.execute(update_query, update_values)

            # Verify the update affected exactly one row
            if cursor.rowcount != 1:
                raise Exception(f"Expected to update 1 row, but affected {cursor.rowcount} rows")

            # Commit the transaction
            cursor.execute("COMMIT")

            # Log the successful update
            print(f"SKU update successful: {sku_id}, fields: {updated_field_names}")

            db.close()

            return {
                "success": True,
                "sku_id": sku_id,
                "message": "SKU updated successfully",
                "updated_fields": updated_field_names,
                "updated_at": datetime.utcnow().isoformat() + "Z"
            }

        except Exception as e:
            # Rollback on any error
            cursor.execute("ROLLBACK")
            raise e

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ValueError as e:
        # Handle validation errors from Pydantic
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
    except Exception as e:
        # Handle unexpected database or system errors
        print(f"SKU update error for {sku_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Update operation failed: {str(e)}")

# =============================================================================
# IMPORT/EXPORT API ENDPOINTS
# =============================================================================

@app.post("/api/import/excel",
         summary="Import Excel File",
         description="Upload and import Excel file with inventory, sales, or SKU data",
         tags=["Import/Export"],
         responses={
             200: {
                 "description": "Import completed successfully",
                 "content": {
                     "application/json": {
                         "example": {
                             "success": True,
                             "filename": "inventory_data.xlsx",
                             "sheets_processed": 2,
                             "records_imported": 150,
                             "errors": [],
                             "warnings": ["Minor data formatting issues corrected"],
                             "summary": {
                                 "total_sheets": 2,
                                 "total_records": 150,
                                 "error_count": 0,
                                 "warning_count": 1,
                                 "success_rate": "100%"
                             }
                         }
                     }
                 }
             },
             400: {"description": "Invalid file format or missing required data"},
             500: {"description": "Import processing failed"}
         })
async def import_excel_file(file: UploadFile = File(...), import_mode: str = Form("append")):
    """
    Import Excel file with comprehensive data validation and processing
    
    Supported Data Types:
    - Inventory levels (burnaby_qty, kentucky_qty by SKU)
    - Sales history (monthly sales with stockout days)
    - SKU master data (description, supplier, cost)
    - Stockout events (dates and durations)
    
    File Requirements:
    - Excel format (.xlsx, .xls)
    - Column headers matching expected schema
    - SKU IDs in consistent format
    - Numeric data properly formatted
    
    Processing Features:
    - Auto-detection of sheet content types
    - Data validation with error/warning reporting
    - Upsert logic (update existing, insert new)
    - Comprehensive import statistics
    
    Returns:
        dict: Import results with success status, statistics, and validation feedback
        
    Raises:
        HTTPException: 400 for invalid files, 500 for processing errors
        
    Business Impact:
        Eliminates manual data entry, ensures data consistency,
        provides audit trail for all imports
    """
    
    # Validate file type
    if not file.filename or not file.filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400, 
            detail="Invalid file format. Please upload an Excel file (.xlsx or .xls)"
        )
    
    try:
        # Read file content
        file_content = await file.read()
        
        # Process import using import_export manager
        result = import_export.import_export_manager.import_excel_file(
            file_content,
            file.filename,
            import_mode
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Excel import failed: {str(e)}"
        )

@app.post("/api/import/csv",
         summary="Import CSV File", 
         description="Upload and import CSV file with data validation",
         tags=["Import/Export"])
async def import_csv_file(file: UploadFile = File(...), import_mode: str = Form("append")):
    """Import CSV file with automatic format detection and validation"""
    
    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Please upload a CSV file"
        )
    
    try:
        file_content = await file.read()
        logger.info(f"CSV IMPORT: Received import_mode parameter: '{import_mode}'")

        result = import_export.import_export_manager.import_csv_file(
            file_content,
            file.filename,
            import_mode
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"CSV import failed: {str(e)}"
        )

@app.post("/api/import/pending-orders",
         summary="Import Pending Orders CSV",
         description="Upload and import pending orders from CSV file with flexible date handling",
         tags=["Import/Export"])
async def import_pending_orders_csv(file: UploadFile = File(...)):
    """Import pending orders from CSV with automatic date calculations"""

    try:
        if not file.filename or not file.filename.lower().endswith('.csv'):
            raise HTTPException(
                status_code=400,
                detail="Invalid file format. Please upload a CSV file"
            )

        file_content = await file.read()

        result = import_export.import_export_manager.import_pending_orders_csv(
            file_content,
            file.filename
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Pending orders CSV import failed: {str(e)}"
        )

@app.post("/api/debug-test",
         summary="Debug Test Endpoint",
         description="Test endpoint to debug endpoint registration issues")
async def debug_test():
    """Debug endpoint to test route registration"""
    return {"message": "Debug test endpoint working", "method": "POST"}

@app.post("/api/pending-orders/import-csv",
         summary="Import Pending Orders from CSV File",
         description="Upload a CSV file and import pending orders with optional replace mode and date format selection",
         tags=["Pending Orders"])
async def import_pending_orders_from_csv(
    file: UploadFile = File(...),
    replace_existing: bool = False,
    date_format: str = "MM/DD/YYYY"
):
    """
    Import pending orders from CSV file upload

    Args:
        file: CSV file with pending orders data
        replace_existing: If True, clear all existing pending orders before import
        date_format: Date format in CSV file - MM/DD/YYYY, DD/MM/YYYY, YYYY-MM-DD, or auto
    """

    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Please upload a CSV file"
        )

    try:
        # Read file content
        file_content = await file.read()
        csv_text = file_content.decode('utf-8')

        # Parse CSV
        import csv
        import io
        from datetime import datetime, timedelta, date
        from typing import Optional

        csv_file = io.StringIO(csv_text)
        reader = csv.DictReader(csv_file)

        # Map user-friendly date format to Python strptime format
        format_mapping = {
            "MM/DD/YYYY": "%m/%d/%Y",
            "DD/MM/YYYY": "%d/%m/%Y",
            "YYYY-MM-DD": "%Y-%m-%d",
            "YYYY/MM/DD": "%Y/%m/%d"
        }

        # Helper function to parse dates with multiple format attempts
        def parse_date_flexible(date_str: str, user_format: str) -> Optional[date]:
            """Parse date string using specified format, with auto-detect fallback"""
            if not date_str:
                return None

            formats_to_try = []
            if user_format == "auto":
                # Try all formats
                formats_to_try = list(format_mapping.values())
            elif user_format in format_mapping:
                # Try user-specified format first, then fallback to others
                formats_to_try = [format_mapping[user_format]] + [f for f in format_mapping.values() if f != format_mapping[user_format]]
            else:
                # Unknown format, try all
                formats_to_try = list(format_mapping.values())

            for fmt in formats_to_try:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue

            return None

        orders = []
        estimated_dates_added = 0

        for row in reader:
            # Parse required fields
            sku_id = row.get('sku_id', '').strip()
            quantity_str = row.get('quantity', '').strip()
            destination = row.get('destination', '').strip().lower()

            # Parse supplier from "order_type" column (CSV naming is confusing)
            # The CSV column is named "order_type" but actually contains supplier name
            supplier = row.get('order_type', '').strip() or None

            if not sku_id or not quantity_str or not destination:
                continue

            try:
                quantity = int(quantity_str)
                # Skip orders with zero or negative quantities
                if quantity <= 0:
                    continue
            except ValueError:
                continue

            # Parse order_date using flexible date format
            order_date_str = row.get('order_date', '').strip()
            if order_date_str:
                order_date = parse_date_flexible(order_date_str, date_format)
                if order_date:
                    # Validate order date is not in the future
                    if order_date > datetime.now().date():
                        order_date = datetime.now().date()
                else:
                    # Could not parse date - default to today
                    order_date = datetime.now().date()
            else:
                # Default to today if no order_date provided (backward compatibility)
                order_date = datetime.now().date()

            # Parse optional expected_arrival using flexible date format
            expected_date_str = row.get('expected_arrival', '').strip()
            if not expected_date_str:
                # Try alternative column names for backward compatibility
                expected_date_str = row.get('expected_date', '').strip()

            if expected_date_str:
                expected_arrival = parse_date_flexible(expected_date_str, date_format)
                if expected_arrival and expected_arrival >= order_date:
                    # Valid expected date
                    expected_arrival_iso = expected_arrival.isoformat()
                    is_estimated = False
                else:
                    # Invalid or date before order date
                    expected_arrival = None
                    expected_arrival_iso = None
                    is_estimated = True
                    estimated_dates_added += 1
            else:
                # No expected date provided - will be calculated from order_date + 120 days
                expected_arrival = None
                expected_arrival_iso = None
                is_estimated = True
                estimated_dates_added += 1

            order = {
                "sku_id": sku_id,
                "quantity": quantity,
                "destination": destination,
                "order_date": order_date.isoformat(),
                "expected_arrival": expected_arrival_iso,
                "is_estimated": is_estimated,
                "order_type": "supplier",
                "supplier": supplier,
                "status": row.get('status', 'ordered').lower(),
                "notes": row.get('notes', '').strip() or None
            }
            orders.append(order)

        if not orders:
            raise HTTPException(
                status_code=400,
                detail="No valid orders found in CSV file"
            )

        # Use the bulk endpoint logic
        try:
            from . import models
        except ImportError:
            import models

        bulk_data = models.BulkPendingInventoryCreate(orders=orders, validate_skus=True)

        db = database.get_database_connection()
        cursor = db.cursor()

        # Handle replace mode - clear existing data if requested
        cleared_count = 0
        if replace_existing:
            cursor.execute("SELECT COUNT(*) FROM pending_inventory")
            cleared_count = cursor.fetchone()[0]
            cursor.execute("DELETE FROM pending_inventory")
            logger.info(f"Replace mode: cleared {cleared_count} existing pending orders")

        imported_count = 0
        error_count = 0
        errors = []
        successful_imports = []
        failed_imports = []
        batch_id = str(uuid.uuid4())

        # Validate SKUs
        all_skus = [order["sku_id"] for order in orders]
        placeholders = ','.join(['%s'] * len(all_skus))
        cursor.execute(f"SELECT sku_id FROM skus WHERE sku_id IN ({placeholders})", all_skus)
        valid_skus = {row[0] for row in cursor.fetchall()}

        invalid_skus = set(all_skus) - valid_skus

        # Track invalid SKUs as failed imports
        for order_data in orders:
            if order_data["sku_id"] in invalid_skus:
                failed_imports.append({
                    "sku_id": order_data["sku_id"],
                    "quantity": order_data["quantity"],
                    "destination": order_data["destination"],
                    "error": "SKU not found in database"
                })

        if invalid_skus:
            errors.append(f"Invalid SKUs found: {', '.join(sorted(invalid_skus))}")

        # Process valid orders
        for order_data in orders:
            if order_data["sku_id"] in valid_skus:
                try:
                    cursor.execute("""
                        INSERT INTO pending_inventory
                        (sku_id, quantity, destination, order_date, expected_arrival,
                         order_type, supplier, status, lead_time_days, is_estimated, notes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        order_data["sku_id"],
                        order_data["quantity"],
                        order_data["destination"],
                        order_data["order_date"],
                        order_data["expected_arrival"],
                        order_data["order_type"],
                        order_data.get("supplier"),
                        order_data["status"],
                        120,  # Default lead time
                        order_data["is_estimated"],
                        order_data.get("notes")
                    ))
                    imported_count += 1

                    # Track successful import
                    successful_imports.append({
                        "sku_id": order_data["sku_id"],
                        "quantity": order_data["quantity"],
                        "destination": order_data["destination"],
                        "expected_arrival": order_data["expected_arrival"],
                        "is_estimated": order_data["is_estimated"],
                        "notes": order_data.get("notes")
                    })

                    if order_data["is_estimated"]:
                        estimated_dates_added += 1
                except Exception as e:
                    error_message = str(e)
                    errors.append(f"Failed to import {order_data['sku_id']}: {error_message}")
                    error_count += 1

                    # Track failed import
                    failed_imports.append({
                        "sku_id": order_data["sku_id"],
                        "quantity": order_data["quantity"],
                        "destination": order_data["destination"],
                        "error": error_message
                    })

        db.commit()
        cursor.close()
        db.close()

        result = {
            "success": True,
            "summary": {
                "total_rows": len(orders),
                "imported": imported_count,
                "failed": error_count + len(invalid_skus),
                "estimated_dates": estimated_dates_added
            },
            "imported_count": imported_count,
            "total_orders": len(orders),
            "estimated_dates_added": estimated_dates_added,
            "errors": errors if errors else [],
            "successful_imports": successful_imports,
            "failed_imports": failed_imports
        }

        # Add replace mode information if used
        if replace_existing:
            result["replace_mode"] = True
            result["cleared_count"] = cleared_count
            result["message"] = f"Replace mode: cleared {cleared_count} existing orders, imported {imported_count} new orders"
        else:
            result["replace_mode"] = False
            result["message"] = f"Append mode: imported {imported_count} new orders"

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"CSV import failed: {str(e)}"
        )

@app.get("/api/export/excel/transfer-orders",
         summary="Export Transfer Orders to Excel",
         description="Generate professional Excel file with transfer recommendations and analysis",
         tags=["Import/Export"],
         responses={
             200: {
                 "description": "Excel file generated successfully",
                 "content": {
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                         "example": "Binary Excel file content"
                     }
                 }
             },
             500: {"description": "Excel generation failed"}
         })
async def export_transfer_orders_excel():
    """
    Export transfer recommendations to professional Excel format
    
    Generated Excel Structure:
    - Transfer Orders: Main recommendations with color-coded priorities
    - Summary: Key statistics and priority distribution
    - Current Inventory: Complete inventory status report
    
    Formatting Features:
    - Color-coded priority levels (Critical=Red, High=Orange, etc.)
    - Professional headers with company branding
    - Auto-sized columns for optimal viewing
    - Frozen header rows for easy scrolling
    - Conditional formatting for visual analysis
    
    File Naming:
    - Format: transfer-orders-YYYY-MM-DD.xlsx
    - Includes generation timestamp
    - Ready for warehouse team distribution
    
    Returns:
        StreamingResponse: Excel file ready for download
        
    Raises:
        HTTPException: 500 if Excel generation fails
        
    Business Use:
        Primary tool for warehouse transfer execution,
        Management reporting, audit documentation
    """
    
    try:
        # Get current transfer recommendations
        recommendations = calculations.calculate_all_transfer_recommendations()
        
        # Generate Excel file
        excel_content = import_export.import_export_manager.export_transfer_recommendations_excel(
            recommendations
        )
        
        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d")
        filename = f"transfer-orders-{timestamp}.xlsx"
        
        # Return as streaming response
        return StreamingResponse(
            io.BytesIO(excel_content),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Excel export failed: {str(e)}"
        )

@app.get("/api/export/csv/transfer-orders",
         summary="Export Transfer Orders to CSV",
         description="Export transfer recommendations in CSV format for data analysis",
         tags=["Import/Export"])
async def export_transfer_orders_csv():
    """Export transfer recommendations to CSV format"""
    
    try:
        # Get recommendations
        recommendations = calculations.calculate_all_transfer_recommendations()
        
        # Generate CSV
        csv_content = import_export.import_export_manager.export_csv(
            recommendations,
            "transfer-orders"
        )
        
        # Create filename
        timestamp = datetime.now().strftime("%Y-%m-%d")
        filename = f"transfer-orders-{timestamp}.csv"
        
        return StreamingResponse(
            io.BytesIO(csv_content),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"CSV export failed: {str(e)}"
        )

@app.get("/api/export/excel/inventory-status",
         summary="Export Inventory Status Report",
         description="Generate comprehensive inventory status report in Excel format",
         tags=["Import/Export"])
async def export_inventory_status_excel():
    """Export current inventory status to Excel with analysis"""
    
    try:
        # Get inventory data from database
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        
        query = """
        SELECT 
            s.sku_id,
            s.description,
            s.supplier,
            s.abc_code,
            s.xyz_code,
            s.cost_per_unit,
            s.transfer_multiple,
            COALESCE(ic.burnaby_qty, 0) as burnaby_qty,
            COALESCE(ic.kentucky_qty, 0) as kentucky_qty,
            COALESCE(ic.burnaby_qty, 0) + COALESCE(ic.kentucky_qty, 0) as total_qty,
            COALESCE(ic.kentucky_qty, 0) * s.cost_per_unit as kentucky_value,
            ic.last_updated,
            CASE 
                WHEN COALESCE(ic.kentucky_qty, 0) = 0 THEN 'OUT_OF_STOCK'
                WHEN COALESCE(ic.kentucky_qty, 0) < 100 THEN 'LOW_STOCK'
                ELSE 'IN_STOCK'
            END as stock_status
        FROM skus s
        LEFT JOIN inventory_current ic ON s.sku_id = ic.sku_id
        WHERE s.status = 'Active'
        ORDER BY ic.kentucky_qty ASC, s.sku_id
        """
        
        cursor.execute(query)
        inventory_data = cursor.fetchall()
        db.close()
        
        # Generate Excel with inventory data
        wb = import_export.Workbook()
        ws = wb.active
        ws.title = "Inventory Status"
        
        # Headers
        headers = [
            "SKU", "Description", "Supplier", "ABC/XYZ", "Unit Cost", "Transfer Multiple",
            "Burnaby Qty", "Kentucky Qty", "Total Qty", "KY Value", "Stock Status", "Last Updated"
        ]
        
        for col, header in enumerate(headers, 1):
            ws.cell(row=1, column=col, value=header)
        
        # Data
        for row, item in enumerate(inventory_data, 2):
            ws.cell(row=row, column=1, value=item['sku_id'])
            ws.cell(row=row, column=2, value=item['description'])
            ws.cell(row=row, column=3, value=item['supplier'])
            ws.cell(row=row, column=4, value=f"{item['abc_code']}{item['xyz_code']}")
            ws.cell(row=row, column=5, value=item['cost_per_unit'])
            ws.cell(row=row, column=6, value=item['transfer_multiple'])
            ws.cell(row=row, column=7, value=item['burnaby_qty'])
            ws.cell(row=row, column=8, value=item['kentucky_qty'])
            ws.cell(row=row, column=9, value=item['total_qty'])
            ws.cell(row=row, column=10, value=item['kentucky_value'])
            ws.cell(row=row, column=11, value=item['stock_status'])
            ws.cell(row=row, column=12, value=item['last_updated'])
        
        # Save to bytes
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        timestamp = datetime.now().strftime("%Y-%m-%d")
        filename = f"inventory-status-{timestamp}.xlsx"
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Inventory export failed: {str(e)}"
        )

@app.get("/api/export/skus",
         summary="Export All SKUs",
         description="Export all SKUs to CSV format with complete master data",
         tags=["Import/Export"],
         responses={
             200: {"description": "CSV file with all SKU data"},
             500: {"description": "Export failed"}
         })
async def export_all_skus():
    """
    Export all SKUs to CSV format with complete master data

    Returns:
        StreamingResponse: CSV file containing all SKU records
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        # Get all SKUs with complete data
        query = """
        SELECT
            sku_id,
            description,
            supplier,
            cost_per_unit,
            status,
            transfer_multiple,
            abc_code,
            xyz_code,
            category,
            created_at,
            updated_at
        FROM skus
        ORDER BY sku_id
        """

        cursor.execute(query)
        skus = cursor.fetchall()
        cursor.close()
        db.close()

        # Convert to CSV
        import csv
        import io
        from datetime import datetime

        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        headers = [
            'sku_id', 'description', 'supplier', 'cost_per_unit', 'status',
            'transfer_multiple', 'abc_code', 'xyz_code', 'category',
            'created_at', 'updated_at'
        ]
        writer.writerow(headers)

        # Write data
        for sku in skus:
            writer.writerow([
                sku['sku_id'],
                sku['description'],
                sku['supplier'],
                sku['cost_per_unit'],
                sku['status'],
                sku['transfer_multiple'],
                sku['abc_code'],
                sku['xyz_code'],
                sku['category'],
                sku['created_at'],
                sku['updated_at']
            ])

        # Prepare response
        output.seek(0)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        filename = f"all-skus-{timestamp}.csv"

        return StreamingResponse(
            io.BytesIO(output.getvalue().encode('utf-8')),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        logger.error(f"SKU export failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"SKU export failed: {str(e)}"
        )

# =============================================================================
# SKU MANAGEMENT ENDPOINTS
# =============================================================================

@app.post("/api/skus/{sku_id}/delete",
           summary="Delete SKU with Cascade",
           description="Permanently delete a SKU and all associated data",
           tags=["SKU Management"],
           responses={
               200: {"description": "SKU deleted successfully"},
               404: {"description": "SKU not found"},
               500: {"description": "Deletion failed due to database error"}
           })
async def delete_sku(sku_id: str):
    """
    Delete a SKU with cascade deletion of all related records
    
    Cascade Deletion Order:
    1. monthly_sales records (historical sales data)
    2. inventory_current records (current stock levels)
    3. skus record (master SKU data)
    
    Parameters:
        sku_id (str): The SKU identifier to delete
        
    Returns:
        dict: Simple deletion confirmation
            
    Raises:
        HTTPException: 404 if SKU not found, 500 for database errors
    """
    try:
        logger.info(f"DELETE SKU REQUEST: Starting deletion for SKU {sku_id}")
        db = database.get_database_connection()
        logger.info(f"DELETE SKU REQUEST: Database connection established")
        cursor = db.cursor(pymysql.cursors.DictCursor)
        
        # Start transaction for atomic deletion
        db.begin()
        logger.info(f"DELETE SKU REQUEST: Transaction started")
        
        # First verify SKU exists
        cursor.execute("SELECT sku_id, description FROM skus WHERE sku_id = %s", (sku_id,))
        sku_data = cursor.fetchone()
        logger.info(f"DELETE SKU REQUEST: SKU lookup result: {sku_data}")
        
        if not sku_data:
            db.rollback()
            logger.warning(f"DELETE SKU REQUEST: SKU {sku_id} not found")
            raise HTTPException(status_code=404, detail=f"SKU {sku_id} not found")
        
        # Delete related records in proper order
        cursor.execute("DELETE FROM monthly_sales WHERE sku_id = %s", (sku_id,))
        cursor.execute("DELETE FROM inventory_current WHERE sku_id = %s", (sku_id,))
        cursor.execute("DELETE FROM skus WHERE sku_id = %s", (sku_id,))
        
        # Commit transaction
        db.commit()
        
        cursor.close()
        db.close()
        
        return {
            "success": True,
            "message": f"SKU {sku_id} deleted successfully",
            "sku_id": sku_data["sku_id"],
            "description": sku_data["description"]
        }
        
    except HTTPException:
        if 'db' in locals():
            db.rollback()
        raise
    except Exception as e:
        if 'db' in locals():
            db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"SKU deletion failed: {str(e)}"
        )

@app.post("/api/skus/bulk-delete",
          summary="Bulk Delete Test SKUs",
          description="Delete multiple SKUs matching test patterns (TEST-, DEMO-, SAMPLE-)",
          tags=["SKU Management"],
          responses={
              200: {"description": "Bulk deletion completed"},
              400: {"description": "No matching SKUs found"},
              500: {"description": "Bulk deletion failed"}
          })
async def bulk_delete_test_skus():
    """
    Bulk delete SKUs matching test patterns for development cleanup
    
    Patterns: TEST-%, DEMO-%, SAMPLE-%
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        
        # Find test SKUs
        patterns = ['TEST-%', 'DEMO-%', 'SAMPLE-%']
        pattern_conditions = " OR ".join(["sku_id LIKE %s" for _ in patterns])
        find_query = f"SELECT sku_id, description FROM skus WHERE {pattern_conditions}"
        
        cursor.execute(find_query, patterns)
        matching_skus = cursor.fetchall()
        
        if not matching_skus:
            raise HTTPException(status_code=400, detail="No test SKUs found")
        
        # Start transaction for bulk deletion
        db.begin()
        
        # Delete each matching SKU with cascade
        deleted_count = 0
        for sku in matching_skus:
            sku_id = sku['sku_id']
            cursor.execute("DELETE FROM monthly_sales WHERE sku_id = %s", (sku_id,))
            cursor.execute("DELETE FROM inventory_current WHERE sku_id = %s", (sku_id,))
            cursor.execute("DELETE FROM skus WHERE sku_id = %s", (sku_id,))
            deleted_count += 1
        
        # Commit all deletions
        db.commit()
        
        cursor.close()
        db.close()
        
        return {
            "success": True,
            "message": f"Deleted {deleted_count} test SKUs",
            "deleted_count": deleted_count
        }
        
    except HTTPException:
        if 'db' in locals():
            db.rollback()
        raise
    except Exception as e:
        if 'db' in locals():
            db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Bulk deletion failed: {str(e)}"
        )

@app.post("/api/skus/delete-all",
          summary="Delete All SKUs",
          description="Delete ALL SKUs from the database (DANGEROUS OPERATION)",
          tags=["SKU Management"],
          responses={
              200: {"description": "All SKUs deleted successfully"},
              400: {"description": "No SKUs found"},
              500: {"description": "Deletion failed"}
          })
async def delete_all_skus():
    """
    Delete ALL SKUs from the database - DANGEROUS OPERATION

    This will delete:
    - All SKU master records
    - All associated sales history
    - All inventory records

    WARNING: This action cannot be undone!
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        # First, count all SKUs to report how many will be deleted
        cursor.execute("SELECT COUNT(*) as total FROM skus")
        total_count = cursor.fetchone()['total']

        if total_count == 0:
            raise HTTPException(status_code=400, detail="No SKUs found in database")

        # Start transaction for complete deletion
        db.begin()

        # Delete all data in correct order (respecting foreign key constraints)
        # 1. Delete monthly sales data
        cursor.execute("DELETE FROM monthly_sales")
        sales_deleted = cursor.rowcount

        # 2. Delete inventory records
        cursor.execute("DELETE FROM inventory_current")
        inventory_deleted = cursor.rowcount

        # 3. Delete pending inventory
        cursor.execute("DELETE FROM pending_inventory")
        pending_deleted = cursor.rowcount

        # 4. Delete all SKUs (master records)
        cursor.execute("DELETE FROM skus")
        skus_deleted = cursor.rowcount

        # Commit all deletions
        db.commit()

        cursor.close()
        db.close()

        return {
            "success": True,
            "message": f"Successfully deleted all {skus_deleted} SKUs and associated data",
            "deleted_count": skus_deleted,
            "details": {
                "skus_deleted": skus_deleted,
                "sales_records_deleted": sales_deleted,
                "inventory_records_deleted": inventory_deleted,
                "pending_orders_deleted": pending_deleted
            }
        }

    except HTTPException:
        if 'db' in locals():
            db.rollback()
        raise
    except Exception as e:
        if 'db' in locals():
            db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Delete all operation failed: {str(e)}"
        )

# ===================================================================
# STOCKOUT MANAGEMENT API ENDPOINTS
# ===================================================================

@app.post("/api/skus/validate",
          summary="Validate SKU List", 
          description="Validate a list of SKUs against the database",
          tags=["Stockout Management"],
          responses={
              200: {"description": "SKU validation results"},
              422: {"description": "Invalid input format"}
          })
async def validate_skus(request: dict):
    """
    Validate a list of SKUs against the database
    
    Args:
        request: Dictionary containing 'skus' list
        
    Returns:
        Dictionary with valid_skus and invalid_skus lists
        
    Example:
        POST /api/skus/validate
        {
            "skus": ["CHG-001", "CBL-002", "INVALID-SKU"]
        }
    """
    try:
        skus = request.get('skus', [])
        if not isinstance(skus, list):
            raise HTTPException(status_code=422, detail="SKUs must be provided as a list")
        
        if not skus:
            return {"valid_skus": [], "invalid_skus": []}
        
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        
        # Query existing SKUs
        placeholders = ','.join(['%s'] * len(skus))
        query = f"""
            SELECT sku_id, description, status 
            FROM skus 
            WHERE sku_id IN ({placeholders})
        """
        
        cursor.execute(query, skus)
        found_skus = cursor.fetchall()
        found_sku_ids = {sku['sku_id'] for sku in found_skus}
        
        # Separate valid and invalid SKUs
        valid_skus = [sku for sku in found_skus]
        invalid_skus = [sku for sku in skus if sku not in found_sku_ids]
        
        cursor.close()
        db.close()
        
        return {
            "valid_skus": valid_skus,
            "invalid_skus": invalid_skus,
            "total_requested": len(skus),
            "valid_count": len(valid_skus),
            "invalid_count": len(invalid_skus)
        }
        
    except Exception as e:
        logger.error(f"SKU validation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"SKU validation failed: {str(e)}"
        )

@app.post("/api/stockouts/bulk-update",
          summary="Bulk Update Stockout Status",
          description="Update stockout status for multiple SKUs",
          tags=["Stockout Management"],
          responses={
              200: {"description": "Bulk update completed successfully"},
              400: {"description": "Invalid input data"},
              500: {"description": "Update operation failed"}
          })
async def bulk_update_stockout_status(request: dict):
    """
    Bulk update stockout status for multiple SKUs
    
    Args:
        request: Dictionary containing update parameters
            - skus: List of SKU IDs to update
            - status: 'out' or 'in' 
            - warehouse: 'kentucky', 'burnaby', or 'both'
            - date: Date string (YYYY-MM-DD)
            - notes: Optional notes for the update
            
    Returns:
        Dictionary with update results and statistics
        
    Example:
        POST /api/stockouts/bulk-update
        {
            "skus": ["CHG-001", "CBL-002"],
            "status": "out",
            "warehouse": "kentucky", 
            "date": "2024-03-28",
            "notes": "Morning stockout check"
        }
    """
    try:
        # Validate input
        required_fields = ['skus', 'status', 'warehouse', 'date']
        for field in required_fields:
            if field not in request:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        skus = request['skus']
        status = request['status']
        warehouse = request['warehouse']
        date_str = request['date']
        notes = request.get('notes', '')
        
        # Validate parameters
        if not isinstance(skus, list) or not skus:
            raise HTTPException(status_code=400, detail="SKUs must be a non-empty list")
        
        if status not in ['out', 'in']:
            raise HTTPException(status_code=400, detail="Status must be 'out' or 'in'")
            
        if warehouse not in ['kentucky', 'burnaby', 'both']:
            raise HTTPException(status_code=400, detail="Warehouse must be 'kentucky', 'burnaby', or 'both'")
        
        # Parse date
        from datetime import datetime
        try:
            stockout_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Date must be in YYYY-MM-DD format")
        
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        
        # Generate batch ID for tracking
        import uuid
        batch_id = str(uuid.uuid4())
        
        # Start transaction
        db.begin()
        
        updated_count = 0
        warehouses = ['kentucky', 'burnaby'] if warehouse == 'both' else [warehouse]
        
        for sku_id in skus:
            for wh in warehouses:
                if status == 'out':
                    # Check if SKU is already out of stock for this warehouse (any unresolved stockout)
                    cursor.execute("""
                        SELECT sku_id, stockout_date FROM stockout_dates
                        WHERE sku_id = %s AND warehouse = %s AND is_resolved = FALSE
                    """, (sku_id, wh))

                    existing_stockout = cursor.fetchone()
                    if existing_stockout:
                        logger.warning(f"SKU {sku_id} is already marked as out of stock for {wh} warehouse since {existing_stockout['stockout_date']}. Skipping duplicate entry.")
                        continue  # Skip this SKU/warehouse combination

                    # Mark as out of stock
                    cursor.execute("""
                        INSERT INTO stockout_dates (sku_id, warehouse, stockout_date, is_resolved)
                        VALUES (%s, %s, %s, FALSE)
                        ON DUPLICATE KEY UPDATE
                            stockout_date = VALUES(stockout_date),
                            is_resolved = FALSE,
                            resolved_date = NULL
                    """, (sku_id, wh, stockout_date))
                    
                    # Update last stockout date in SKUs table
                    cursor.execute("""
                        UPDATE skus 
                        SET last_stockout_date = %s, updated_at = NOW()
                        WHERE sku_id = %s
                    """, (stockout_date, sku_id))
                    
                else:  # status == 'in'
                    # Mark as back in stock (resolve stockout)
                    cursor.execute("""
                        UPDATE stockout_dates
                        SET is_resolved = TRUE, resolved_date = %s
                        WHERE sku_id = %s AND warehouse = %s AND is_resolved = FALSE
                    """, (stockout_date, sku_id, wh))

                # Log the update (only if we didn't skip due to duplicate)
                cursor.execute("""
                    INSERT INTO stockout_updates_log
                    (update_batch_id, sku_id, warehouse, action, new_status, stockout_date,
                     resolution_date, update_source, user_notes, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (
                    batch_id,
                    sku_id,
                    wh,
                    'mark_out' if status == 'out' else 'mark_in',
                    'out_of_stock' if status == 'out' else 'in_stock',
                    stockout_date,
                    stockout_date if status == 'in' else None,
                    'quick_ui',
                    notes
                ))

                updated_count += 1
        
        # Commit transaction
        db.commit()
        cursor.close()
        db.close()
        
        logger.info(f"Bulk stockout update completed: {updated_count} updates for batch {batch_id}")
        
        return {
            "success": True,
            "batch_id": batch_id,
            "updated_count": updated_count,
            "skus_processed": len(skus),
            "warehouses_processed": len(warehouses),
            "status": status,
            "date": date_str,
            "notes": notes
        }
        
    except HTTPException:
        if 'db' in locals():
            db.rollback()
        raise
    except Exception as e:
        if 'db' in locals():
            db.rollback()
        logger.error(f"Bulk stockout update failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Bulk stockout update failed: {str(e)}"
        )

@app.get("/api/stockouts/current",
         summary="Get Current Stockouts",
         description="Retrieve all currently unresolved stockouts",
         tags=["Stockout Management"],
         responses={
             200: {"description": "List of current stockouts"},
             500: {"description": "Failed to retrieve stockouts"}
         })
async def get_current_stockouts():
    """
    Get all currently unresolved stockouts with urgency levels
    
    Returns:
        List of stockout records with calculated urgency and days out
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        
        # Query stockout_dates directly with basic SKU information
        query = """
            SELECT
                sd.sku_id,
                s.description,
                s.status,
                s.category,
                sd.warehouse,
                sd.stockout_date,
                DATEDIFF(CURDATE(), sd.stockout_date) as days_out,
                CASE
                    WHEN DATEDIFF(CURDATE(), sd.stockout_date) >= 30 THEN 'CRITICAL'
                    WHEN DATEDIFF(CURDATE(), sd.stockout_date) >= 14 THEN 'HIGH'
                    WHEN DATEDIFF(CURDATE(), sd.stockout_date) >= 7 THEN 'MEDIUM'
                    ELSE 'LOW'
                END as urgency_level,
                s.cost_per_unit,
                ic.burnaby_qty,
                ic.kentucky_qty
            FROM stockout_dates sd
            INNER JOIN skus s ON sd.sku_id = s.sku_id
            LEFT JOIN inventory_current ic ON s.sku_id = ic.sku_id
            WHERE sd.is_resolved = FALSE
            ORDER BY
                CASE
                    WHEN DATEDIFF(CURDATE(), sd.stockout_date) >= 30 THEN 1
                    WHEN DATEDIFF(CURDATE(), sd.stockout_date) >= 14 THEN 2
                    WHEN DATEDIFF(CURDATE(), sd.stockout_date) >= 7 THEN 3
                    ELSE 4
                END,
                sd.stockout_date ASC
        """
        
        cursor.execute(query)
        stockouts = cursor.fetchall()
        
        cursor.close()
        db.close()
        
        return stockouts
        
    except Exception as e:
        logger.error(f"Failed to get current stockouts: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve current stockouts: {str(e)}"
        )

@app.get("/api/stockouts/recent-updates",
         summary="Get Recent Stockout Updates", 
         description="Retrieve recent stockout status updates",
         tags=["Stockout Management"],
         responses={
             200: {"description": "List of recent updates"},
             500: {"description": "Failed to retrieve updates"}
         })
async def get_recent_stockout_updates(limit: int = 10):
    """
    Get recent stockout status updates for audit trail
    
    Args:
        limit: Maximum number of updates to return (default 10)
        
    Returns:
        List of recent update records grouped by batch
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        
        # Get recent updates grouped by batch
        query = """
            SELECT 
                update_batch_id as batch_id,
                action,
                warehouse,
                COUNT(*) as sku_count,
                MIN(created_at) as created_at,
                MAX(user_notes) as notes,
                update_source
            FROM stockout_updates_log
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            GROUP BY update_batch_id, action, warehouse, update_source
            ORDER BY created_at DESC
            LIMIT %s
        """
        
        cursor.execute(query, (limit,))
        updates = cursor.fetchall()
        
        cursor.close()
        db.close()
        
        return updates
        
    except Exception as e:
        logger.error(f"Failed to get recent updates: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve recent updates: {str(e)}"
        )

@app.post("/api/stockouts/undo/{batch_id}",
          summary="Undo Stockout Update",
          description="Reverse a previous stockout update batch",
          tags=["Stockout Management"], 
          responses={
              200: {"description": "Update successfully undone"},
              404: {"description": "Batch not found"},
              500: {"description": "Undo operation failed"}
          })
async def undo_stockout_update(batch_id: str):
    """
    Undo a previous stockout update by batch ID
    
    Args:
        batch_id: The batch ID of the update to reverse
        
    Returns:
        Dictionary with undo operation results
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        
        # Get the updates to undo
        cursor.execute("""
            SELECT sku_id, warehouse, action, stockout_date, resolution_date
            FROM stockout_updates_log
            WHERE update_batch_id = %s
            ORDER BY created_at DESC
        """, (batch_id,))
        
        updates = cursor.fetchall()
        
        if not updates:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        # Start transaction for undo
        db.begin()
        
        undone_count = 0
        undo_batch_id = str(uuid.uuid4())
        
        for update in updates:
            sku_id = update['sku_id']
            warehouse = update['warehouse']
            action = update['action']
            
            if action == 'mark_out':
                # Reverse: mark as resolved/in stock
                cursor.execute("""
                    UPDATE stockout_dates 
                    SET is_resolved = TRUE, resolved_date = CURDATE()
                    WHERE sku_id = %s AND warehouse = %s 
                        AND stockout_date = %s AND is_resolved = FALSE
                """, (sku_id, warehouse, update['stockout_date']))
                
                new_action = 'mark_in'
                new_status = 'in_stock'
                
            elif action == 'mark_in':
                # Reverse: mark as out of stock again
                cursor.execute("""
                    UPDATE stockout_dates 
                    SET is_resolved = FALSE, resolved_date = NULL
                    WHERE sku_id = %s AND warehouse = %s 
                        AND stockout_date = %s
                """, (sku_id, warehouse, update['stockout_date']))
                
                new_action = 'mark_out'
                new_status = 'out_of_stock'
            
            # Log the undo action
            cursor.execute("""
                INSERT INTO stockout_updates_log 
                (update_batch_id, sku_id, warehouse, action, new_status, 
                 stockout_date, update_source, user_notes, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                undo_batch_id,
                sku_id,
                warehouse, 
                new_action,
                new_status,
                update['stockout_date'],
                'quick_ui',
                f'Undo of batch {batch_id}'
            ))
            
            undone_count += 1
        
        # Commit undo transaction
        db.commit()
        cursor.close()
        db.close()
        
        logger.info(f"Undid stockout update batch {batch_id}: {undone_count} operations reversed")
        
        return {
            "success": True,
            "undone_batch_id": batch_id,
            "new_batch_id": undo_batch_id,
            "undone_count": undone_count
        }
        
    except HTTPException:
        if 'db' in locals():
            db.rollback()
        raise
    except Exception as e:
        if 'db' in locals():
            db.rollback()
        logger.error(f"Undo operation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Undo operation failed: {str(e)}"
        )

@app.post("/api/import/stockout-history",
          summary="Import Historical Stockout Data",
          description="Import historical stockout data from CSV file",
          tags=["Stockout Management"],
          responses={
              200: {"description": "CSV import completed successfully"},
              400: {"description": "Invalid file format or data"},
              500: {"description": "Import operation failed"}
          })
async def import_stockout_history(file: UploadFile = File(...)):
    """
    Import historical stockout data from CSV file with warehouse specification support

    Supported CSV formats:

    Legacy format (3 columns) - defaults to Kentucky warehouse:
    - Column 1: SKU ID
    - Column 2: Date out of stock (YYYY-MM-DD)
    - Column 3: Date back in stock (YYYY-MM-DD or blank for ongoing)

    Enhanced format (4 columns) - warehouse can be specified:
    - Column 1: SKU ID
    - Column 2: Date out of stock (YYYY-MM-DD)
    - Column 3: Date back in stock (YYYY-MM-DD or blank for ongoing)
    - Column 4: Warehouse ('kentucky', 'burnaby', or 'both')

    Business Rules:
    - Warehouse values are case-insensitive
    - 'both' creates separate records for both warehouses
    - Legacy files without warehouse column default to 'kentucky'
    - Invalid warehouse values generate clear error messages

    Args:
        file: CSV file upload containing stockout history data

    Returns:
        Dictionary with import results and detailed statistics including:
        - success: boolean indicating if any records were imported
        - imported_count: total number of stockout records created
        - error_count: number of rows with validation errors
        - total_rows: total rows processed
        - batch_id: unique identifier for this import operation
        - filename: name of the uploaded file
        - errors: list of first 10 error messages for troubleshooting
    """
    try:
        # Validate file type
        if not file.filename.lower().endswith('.csv'):
            raise HTTPException(status_code=400, detail="File must be a CSV")

        # Read CSV content
        content = await file.read()
        decoded_content = content.decode('utf-8')

        import csv
        import io
        import uuid
        from datetime import datetime

        # Parse CSV
        csv_reader = csv.reader(io.StringIO(decoded_content))

        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        # Start transaction
        db.begin()

        imported_count = 0
        error_count = 0
        batch_id = str(uuid.uuid4())
        errors = []

        # Valid warehouse values (case-insensitive)
        valid_warehouses = {'kentucky', 'burnaby', 'both'}

        for row_num, row in enumerate(csv_reader, 1):
            try:
                if len(row) < 2:
                    errors.append(f"Row {row_num}: Insufficient columns (minimum 2 required: SKU, Date_Out)")
                    error_count += 1
                    continue

                sku_id = row[0].strip()
                date_out_str = row[1].strip()
                date_in_str = row[2].strip() if len(row) > 2 else ''

                # Handle warehouse column (4th column) with backward compatibility
                warehouse_input = 'kentucky'  # Default for legacy files
                if len(row) > 3 and row[3].strip():
                    warehouse_raw = row[3].strip().lower()
                    if warehouse_raw in valid_warehouses:
                        warehouse_input = warehouse_raw
                    else:
                        errors.append(f"Row {row_num}: Invalid warehouse '{row[3]}'. Valid options: kentucky, burnaby, both")
                        error_count += 1
                        continue

                if not sku_id or not date_out_str:
                    errors.append(f"Row {row_num}: Missing required fields (SKU and Date_Out are mandatory)")
                    error_count += 1
                    continue

                # Validate SKU exists
                cursor.execute("SELECT sku_id FROM skus WHERE sku_id = %s", (sku_id,))
                if not cursor.fetchone():
                    errors.append(f"Row {row_num}: SKU '{sku_id}' not found in database")
                    error_count += 1
                    continue

                # Parse dates
                try:
                    date_out = datetime.strptime(date_out_str, '%Y-%m-%d').date()
                except ValueError:
                    errors.append(f"Row {row_num}: Invalid date format for Date_Out '{date_out_str}' (expected YYYY-MM-DD)")
                    error_count += 1
                    continue

                date_in = None
                is_resolved = False
                if date_in_str:
                    try:
                        date_in = datetime.strptime(date_in_str, '%Y-%m-%d').date()
                        is_resolved = True
                    except ValueError:
                        errors.append(f"Row {row_num}: Invalid date format for Date_Back_In '{date_in_str}' (expected YYYY-MM-DD)")
                        error_count += 1
                        continue

                # Determine which warehouses to create records for
                warehouses_to_process = []
                if warehouse_input == 'both':
                    warehouses_to_process = ['kentucky', 'burnaby']
                else:
                    warehouses_to_process = [warehouse_input]

                # Create stockout records for specified warehouse(s)
                for warehouse in warehouses_to_process:
                    # Insert stockout record
                    cursor.execute("""
                        INSERT INTO stockout_dates
                        (sku_id, warehouse, stockout_date, is_resolved, resolved_date)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            is_resolved = VALUES(is_resolved),
                            resolved_date = VALUES(resolved_date)
                    """, (sku_id, warehouse, date_out, is_resolved, date_in))

                    # Log the import
                    cursor.execute("""
                        INSERT INTO stockout_updates_log
                        (update_batch_id, sku_id, warehouse, action, new_status,
                         stockout_date, resolution_date, update_source, user_notes, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """, (
                        batch_id,
                        sku_id,
                        warehouse,
                        'mark_in' if is_resolved else 'mark_out',
                        'in_stock' if is_resolved else 'out_of_stock',
                        date_out,
                        date_in,
                        'csv_import',
                        f'Historical import from {file.filename} (warehouse: {warehouse_input})'
                    ))

                    imported_count += 1

            except Exception as e:
                errors.append(f"Row {row_num}: Unexpected error - {str(e)}")
                error_count += 1
                continue
        
        # Commit if any successful imports
        if imported_count > 0:
            db.commit()
        else:
            db.rollback()
        
        cursor.close()
        db.close()
        
        logger.info(f"CSV import completed: {imported_count} imported, {error_count} errors")
        
        return {
            "success": imported_count > 0,
            "imported_count": imported_count,
            "error_count": error_count,
            "total_rows": imported_count + error_count,
            "batch_id": batch_id,
            "filename": file.filename,
            "errors": errors[:10]  # Return first 10 errors
        }
        
    except HTTPException:
        if 'db' in locals():
            db.rollback()
        raise
    except Exception as e:
        if 'db' in locals():
            db.rollback()
        logger.error(f"CSV import failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"CSV import failed: {str(e)}"
        )

@app.post("/api/sync-stockout-days",
          summary="Synchronize Stockout Days",
          description="Aggregate stockout periods from stockout_dates table into monthly_sales",
          tags=["Stockout Management"],
          responses={
              200: {
                  "description": "Synchronization completed successfully",
                  "content": {
                      "application/json": {
                          "example": {
                              "success": True,
                              "processed_records": 1234,
                              "processed_skus": 567,
                              "errors": [],
                              "duration_seconds": 5.23,
                              "message": "Stockout days synchronized successfully"
                          }
                      }
                  }
              },
              500: {"description": "Synchronization operation failed"}
          })
async def sync_stockout_days():
    """
    Synchronize all stockout days from stockout_dates table to monthly_sales table

    This endpoint processes all stockout periods and updates the monthly_sales table
    with accurate stockout day counts for both warehouses. It should be run:
    - After importing new stockout history data
    - When discrepancies are found in stockout calculations
    - As part of monthly data maintenance

    Business Process:
    1. Queries all stockout periods from stockout_dates table
    2. Calculates monthly aggregations for each SKU and warehouse
    3. Handles partial months and overlapping periods correctly
    4. Updates both burnaby_stockout_days and kentucky_stockout_days fields
    5. Creates missing monthly_sales records if needed

    Performance Considerations:
    - Processes data in batches to prevent memory issues
    - Uses efficient SQL queries with proper indexing
    - Includes progress logging for large datasets
    - Completes in under 30 seconds for typical dataset sizes

    Returns:
        Dictionary with operation results including:
        - success: boolean indicating if operation completed successfully
        - processed_records: number of monthly_sales records updated
        - processed_skus: number of unique SKUs processed
        - errors: list of any errors encountered during processing
        - duration_seconds: time taken to complete the operation
        - message: human-readable summary of the operation

    Raises:
        HTTPException: 500 if synchronization fails with detailed error message
    """
    try:
        logger.info("Starting stockout days synchronization via API endpoint")

        # Import the sync function from database module
        from . import database

        # Execute the synchronization
        result = database.sync_all_stockout_days()

        # Add human-readable message based on results
        if result["success"]:
            if result["processed_records"] > 0:
                message = f"Successfully synchronized {result['processed_records']} records for {result['processed_skus']} SKUs"
            else:
                message = "No stockout data found to synchronize"
        else:
            message = f"Synchronization failed with {len(result['errors'])} errors"

        result["message"] = message

        # Log completion
        logger.info(f"Stockout synchronization API completed: {message}")

        return result

    except ImportError as e:
        error_msg = f"Failed to import database module: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )
    except Exception as e:
        error_msg = f"Stockout synchronization failed: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )

@app.post("/api/recalculate-corrected-demands",
          summary="Recalculate Corrected Demands",
          description="Recalculate and update corrected demand values for all SKUs using stockout correction",
          tags=["Stockout Management"],
          responses={
              200: {
                  "description": "Recalculation completed successfully",
                  "content": {
                      "application/json": {
                          "example": {
                              "success": True,
                              "updated_records": 3153,
                              "errors": [],
                              "duration_seconds": 12.45,
                              "message": "Successfully recalculated corrected demand for 3153 records"
                          }
                      }
                  }
              },
              500: {
                  "description": "Recalculation failed",
                  "content": {
                      "application/json": {
                          "example": {
                              "detail": "Recalculation failed: Database connection error"
                          }
                      }
                  }
              }
          })
async def recalculate_corrected_demands():
    """
    Recalculate and update corrected demand values for all SKUs and months

    This endpoint processes all monthly sales data and applies the stockout correction
    algorithm to calculate proper corrected demand values. It reads sales data and
    stockout days, then stores the corrected values in the corrected_demand_burnaby
    and corrected_demand_kentucky fields.

    Business Logic:
    1. Reads all monthly sales records with sales or stockout data
    2. Calculates corrected demand using availability rate with 30% floor
    3. Applies 50% increase cap for very low availability as safeguard
    4. Updates database with actual corrected values instead of raw sales
    5. Handles leap years and variable month lengths correctly

    Use Cases:
    - After fixing stockout correction algorithm
    - When corrected_demand fields contain raw sales instead of corrected values
    - As part of data maintenance and integrity checks
    - Before generating transfer recommendations

    Algorithm:
    - corrected_demand = sales / max(availability_rate, 0.3)
    - availability_rate = (days_in_month - stockout_days) / days_in_month
    - Cap correction at 1.5x raw sales for extreme cases

    Performance:
    - Processes ~3000 records in under 15 seconds
    - Uses batch updates with proper transaction handling
    - Includes detailed error reporting for failed updates

    Returns:
        Dictionary with operation results including:
        - success: boolean indicating if operation completed successfully
        - updated_records: number of monthly_sales records updated
        - errors: list of any errors encountered during processing
        - duration_seconds: time taken to complete the operation
        - message: human-readable summary of the operation

    Raises:
        HTTPException: 500 if recalculation fails with detailed error message
    """
    try:
        logger.info("Starting corrected demand recalculation via API endpoint")

        # Import the recalculation function from database module
        from . import database

        # Execute the recalculation
        result = database.recalculate_all_corrected_demands()

        # Add human-readable message based on results
        if result["success"]:
            if result["updated_records"] > 0:
                message = f"Successfully recalculated corrected demand for {result['updated_records']} records"
            else:
                message = "No records found to recalculate"
        else:
            message = f"Recalculation failed with {len(result.get('errors', []))} errors"

        result["message"] = message

        # Log completion
        logger.info(f"Corrected demand recalculation API completed: {message}")

        return result

    except ImportError as e:
        error_msg = f"Failed to import database module: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )
    except Exception as e:
        error_msg = f"Corrected demand recalculation failed: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )

# ===================================================================
# PENDING ORDERS API ENDPOINTS
# ===================================================================

@app.get("/api/pending-orders",
         summary="Get All Pending Orders",
         description="Retrieve all pending inventory orders with analysis data",
         tags=["Pending Orders"])
async def get_pending_orders(
    status: Optional[str] = None,
    destination: Optional[str] = None,
    order_type: Optional[str] = None,
    overdue_only: bool = False,
    limit: Optional[int] = None,
    offset: Optional[int] = 0
):
    """
    Retrieve pending orders with filtering options

    Args:
        status: Filter by order status (ordered/shipped/received/cancelled)
        destination: Filter by destination warehouse (burnaby/kentucky)
        order_type: Filter by order type (supplier/transfer)
        overdue_only: Show only overdue orders
        limit: Maximum number of records to return
        offset: Number of records to skip (for pagination)

    Returns:
        List of pending orders with analysis data, total count, and pagination info
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        # Base query for counting total records
        count_query = """
        SELECT COUNT(*) as total FROM v_pending_orders_analysis
        WHERE 1=1
        """
        count_params = []

        # Base query for fetching data
        data_query = """
        SELECT * FROM v_pending_orders_analysis
        WHERE 1=1
        """
        data_params = []

        # Apply filters to both queries
        filter_conditions = ""

        if status:
            filter_conditions += " AND status = %s"
            count_params.append(status.lower())
            data_params.append(status.lower())

        if destination:
            filter_conditions += " AND destination = %s"
            count_params.append(destination.lower())
            data_params.append(destination.lower())

        if order_type:
            filter_conditions += " AND order_type = %s"
            count_params.append(order_type.lower())
            data_params.append(order_type.lower())

        if overdue_only:
            filter_conditions += " AND is_overdue = TRUE"

        # Execute count query
        cursor.execute(count_query + filter_conditions, count_params)
        total_count = cursor.fetchone()['total']

        # Execute data query with pagination
        data_query += filter_conditions + " ORDER BY priority_score DESC, order_date ASC"

        # MySQL LIMIT OFFSET syntax: LIMIT offset, count
        if limit and offset > 0:
            data_query += " LIMIT %s, %s"
            data_params.append(offset)
            data_params.append(limit)
        elif limit:
            data_query += " LIMIT %s"
            data_params.append(limit)

        cursor.execute(data_query, data_params)
        results = cursor.fetchall()

        cursor.close()
        db.close()

        # Calculate pagination metadata
        page_size = limit or total_count
        current_page = (offset // page_size) + 1 if page_size > 0 else 1
        total_pages = (total_count + page_size - 1) // page_size if page_size > 0 else 1

        return {
            "success": True,
            "data": results,
            "count": len(results),
            "total": total_count,
            "page": current_page,
            "pages": total_pages,
            "page_size": page_size
        }

    except Exception as e:
        logger.error(f"Failed to retrieve pending orders: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve pending orders: {str(e)}"
        )

@app.get("/api/pending-orders/summary",
         summary="Get Pending Orders Summary Statistics",
         description="Get aggregated statistics for pending orders",
         tags=["Pending Orders"])
async def get_pending_orders_summary():
    """
    Get aggregated summary statistics for pending orders
    Returns total orders, unique SKUs, and breakdown by destination
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        # Get summary statistics from pending_orders table - updated for aggregation
        summary_query = """
        SELECT
            COUNT(*) as total_orders,
            COUNT(DISTINCT sku_id) as unique_skus,
            SUM(CASE WHEN destination = 'burnaby' THEN 1 ELSE 0 END) as burnaby_orders,
            SUM(CASE WHEN destination = 'kentucky' THEN 1 ELSE 0 END) as kentucky_orders
        FROM pending_inventory
        WHERE status NOT IN ('cancelled', 'received')
        """

        cursor.execute(summary_query)
        summary = cursor.fetchone()

        cursor.close()
        db.close()

        return {
            "success": True,
            "total_orders": summary.get('total_orders', 0),
            "unique_skus": summary.get('unique_skus', 0),
            "burnaby_orders": summary.get('burnaby_orders', 0),
            "kentucky_orders": summary.get('kentucky_orders', 0)
        }

    except Exception as e:
        logger.error(f"Failed to get pending orders summary: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get pending orders summary: {str(e)}"
        )

@app.post("/api/pending-orders",
          summary="Create Pending Order",
          description="Create a new pending inventory order",
          tags=["Pending Orders"])
async def create_pending_order(order: models.PendingInventoryCreate):
    """
    Create a new pending inventory order
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor()

        # Validate SKU exists
        cursor.execute("SELECT sku_id FROM skus WHERE sku_id = %s", (order.sku_id,))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=404,
                detail=f"SKU '{order.sku_id}' not found"
            )

        # Insert new pending order
        insert_query = """
        INSERT INTO pending_inventory (
            sku_id, quantity, destination, order_date, expected_arrival,
            order_type, status, lead_time_days, is_estimated, notes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        cursor.execute(insert_query, (
            order.sku_id,
            order.quantity,
            order.destination,
            order.order_date,
            order.expected_arrival,
            order.order_type,
            order.status,
            order.lead_time_days,
            order.is_estimated,
            order.notes
        ))

        order_id = cursor.lastrowid
        db.commit()

        cursor.close()
        db.close()

        return {
            "success": True,
            "message": "Pending order created successfully",
            "id": order_id,
            "sku_id": order.sku_id
        }

    except HTTPException:
        raise
    except Exception as e:
        if 'db' in locals():
            db.rollback()
        logger.error(f"Failed to create pending order: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create pending order: {str(e)}"
        )

@app.post("/api/pending-orders/bulk",
          summary="Bulk Create Pending Orders",
          description="Create multiple pending orders in a single transaction",
          tags=["Pending Orders"])
async def bulk_create_pending_orders(bulk_data: models.BulkPendingInventoryCreate):
    """
    Create multiple pending orders in a single transaction
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor()

        imported_count = 0
        error_count = 0
        errors = []
        batch_id = str(uuid.uuid4())

        # Validate SKUs if requested
        if bulk_data.validate_skus:
            all_skus = [order.sku_id for order in bulk_data.orders]
            placeholders = ','.join(['%s'] * len(all_skus))
            cursor.execute(f"SELECT sku_id FROM skus WHERE sku_id IN ({placeholders})", all_skus)
            valid_skus = {row[0] for row in cursor.fetchall()}

            invalid_skus = set(all_skus) - valid_skus
            if invalid_skus:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid SKUs found: {', '.join(sorted(invalid_skus))}"
                )

        # Insert orders
        insert_query = """
        INSERT INTO pending_inventory (
            sku_id, quantity, destination, order_date, expected_arrival,
            order_type, status, lead_time_days, is_estimated, notes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        for idx, order in enumerate(bulk_data.orders):
            try:
                cursor.execute(insert_query, (
                    order.sku_id,
                    order.quantity,
                    order.destination,
                    order.order_date,
                    order.expected_arrival,
                    order.order_type,
                    order.status,
                    order.lead_time_days,
                    order.is_estimated,
                    order.notes
                ))
                imported_count += 1

            except Exception as e:
                errors.append(f"Order {idx + 1} ({order.sku_id}): {str(e)}")
                error_count += 1
                continue

        if imported_count > 0:
            db.commit()
        else:
            db.rollback()

        cursor.close()
        db.close()

        return {
            "success": imported_count > 0,
            "imported_count": imported_count,
            "error_count": error_count,
            "total_orders": len(bulk_data.orders),
            "batch_id": batch_id,
            "errors": errors[:10]
        }

    except HTTPException:
        if 'db' in locals():
            db.rollback()
        raise
    except Exception as e:
        if 'db' in locals():
            db.rollback()
        logger.error(f"Bulk pending orders creation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Bulk creation failed: {str(e)}"
        )

# ===================================================================
# PENDING ORDERS BULK MANAGEMENT ENDPOINTS
# ===================================================================

@app.get("/api/pending-orders/debug-test-route")
async def test_route():
    """Test route to verify routing works"""
    print("DEBUG: test_route function called")
    return {"message": "Test route works"}

@app.post("/api/admin/clear-pending-orders",
           summary="Clear All Pending Orders",
           description="Delete all pending orders with safety confirmation",
           tags=["Admin"])
async def clear_all_pending_orders():
    """
    Clear all pending orders from the database

    Returns count of deleted records for confirmation
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor()

        # First get count for confirmation
        cursor.execute("SELECT COUNT(*) FROM pending_inventory")
        total_count = cursor.fetchone()[0]

        if total_count == 0:
            return {
                "success": True,
                "message": "No pending orders to delete",
                "deleted_count": 0
            }

        # Delete all pending orders
        cursor.execute("DELETE FROM pending_inventory")
        deleted_count = cursor.rowcount

        db.commit()
        cursor.close()
        db.close()

        logger.info(f"Cleared all pending orders: {deleted_count} records deleted")

        return {
            "success": True,
            "message": f"Successfully deleted {deleted_count} pending orders",
            "deleted_count": deleted_count
        }

    except Exception as e:
        if 'db' in locals():
            db.rollback()
            cursor.close()
            db.close()
        logger.error(f"Failed to clear all pending orders: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear pending orders: {str(e)}"
        )

@app.delete("/api/pending-orders/clear-batch/{batch_id}",
           summary="Clear Pending Orders by Batch",
           description="Delete all pending orders with specific batch ID",
           tags=["Pending Orders"])
async def clear_pending_orders_batch(batch_id: str):
    """
    Clear pending orders by batch ID

    Args:
        batch_id: Batch identifier to delete

    Returns:
        Count of deleted records
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor()

        # First get count for confirmation
        cursor.execute("SELECT COUNT(*) FROM pending_inventory WHERE batch_id = %s", (batch_id,))
        count = cursor.fetchone()[0]

        if count == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No pending orders found with batch ID: {batch_id}"
            )

        # Delete by batch ID
        cursor.execute("DELETE FROM pending_inventory WHERE batch_id = %s", (batch_id,))
        deleted_count = cursor.rowcount

        db.commit()
        cursor.close()
        db.close()

        logger.info(f"Cleared pending orders for batch {batch_id}: {deleted_count} records deleted")

        return {
            "success": True,
            "message": f"Successfully deleted {deleted_count} pending orders from batch {batch_id}",
            "deleted_count": deleted_count,
            "batch_id": batch_id
        }

    except HTTPException:
        raise
    except Exception as e:
        if 'db' in locals():
            db.rollback()
            cursor.close()
            db.close()
        logger.error(f"Failed to clear batch {batch_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear batch: {str(e)}"
        )

@app.delete("/api/pending-orders/clear-sku/{sku_id}",
           summary="Clear Pending Orders by SKU",
           description="Delete all pending orders for a specific SKU",
           tags=["Pending Orders"])
async def clear_pending_orders_sku(sku_id: str):
    """
    Clear all pending orders for a specific SKU

    Args:
        sku_id: SKU identifier to clear orders for

    Returns:
        Count of deleted records
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor()

        # First get count for confirmation
        cursor.execute("SELECT COUNT(*) FROM pending_inventory WHERE sku_id = %s", (sku_id,))
        count = cursor.fetchone()[0]

        if count == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No pending orders found for SKU: {sku_id}"
            )

        # Delete by SKU
        cursor.execute("DELETE FROM pending_inventory WHERE sku_id = %s", (sku_id,))
        deleted_count = cursor.rowcount

        db.commit()
        cursor.close()
        db.close()

        logger.info(f"Cleared pending orders for SKU {sku_id}: {deleted_count} records deleted")

        return {
            "success": True,
            "message": f"Successfully deleted {deleted_count} pending orders for SKU {sku_id}",
            "deleted_count": deleted_count,
            "sku_id": sku_id
        }

    except HTTPException:
        raise
    except Exception as e:
        if 'db' in locals():
            db.rollback()
            cursor.close()
            db.close()
        logger.error(f"Failed to clear SKU {sku_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear SKU orders: {str(e)}"
        )

@app.delete("/api/pending-orders/{order_id}",
           summary="Delete Pending Order",
           description="Delete a pending order",
           tags=["Pending Orders"])
async def delete_pending_order(order_id: int):
    """
    Delete a pending order
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor()

        cursor.execute("DELETE FROM pending_inventory WHERE id = %s", (order_id,))

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Pending order {order_id} not found"
            )

        db.commit()
        cursor.close()
        db.close()

        return {
            "success": True,
            "message": f"Pending order {order_id} deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        if 'db' in locals():
            db.rollback()
        logger.error(f"Failed to delete pending order {order_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete pending order: {str(e)}"
        )

@app.get("/api/pending-orders/{order_id}",
         summary="Get Pending Order Details",
         description="Get detailed information for a specific pending order",
         tags=["Pending Orders"])
async def get_pending_order(order_id: int):
    """
    Get detailed information for a specific pending order
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        query = """
        SELECT * FROM v_pending_orders_analysis
        WHERE id = %s
        """

        cursor.execute(query, (order_id,))
        result = cursor.fetchone()

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Pending order {order_id} not found"
            )

        cursor.close()
        db.close()

        return {
            "success": True,
            "data": result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get pending order {order_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get pending order: {str(e)}"
        )

@app.put("/api/pending-orders/{order_id}",
         summary="Update Pending Order",
         description="Update an existing pending order",
         tags=["Pending Orders"])
async def update_pending_order(order_id: int, updates: models.PendingInventoryUpdate):
    """
    Update an existing pending order
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor()

        # Check if order exists
        cursor.execute("SELECT id FROM pending_inventory WHERE id = %s", (order_id,))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=404,
                detail=f"Pending order {order_id} not found"
            )

        # Build update query dynamically
        update_fields = []
        update_values = []

        for field, value in updates.dict(exclude_unset=True).items():
            if value is not None:
                update_fields.append(f"{field} = %s")
                update_values.append(value)

        if not update_fields:
            raise HTTPException(
                status_code=400,
                detail="No fields to update"
            )

        update_query = f"""
        UPDATE pending_inventory
        SET {', '.join(update_fields)}, updated_at = NOW()
        WHERE id = %s
        """
        update_values.append(order_id)

        cursor.execute(update_query, update_values)

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Pending order {order_id} not found"
            )

        db.commit()
        cursor.close()
        db.close()

        return {
            "success": True,
            "message": f"Pending order {order_id} updated successfully",
            "id": order_id
        }

    except HTTPException:
        raise
    except Exception as e:
        if 'db' in locals():
            db.rollback()
        logger.error(f"Failed to update pending order {order_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update pending order: {str(e)}"
        )

# ===================================================================
# SAFETY STOCK AND COVERAGE TESTING API ENDPOINTS
# ===================================================================

@app.get("/api/test-safety-stock/{sku_id}",
         summary="Test Safety Stock and Coverage Calculations",
         description="Test complete volatility, safety stock, and coverage calculation system",
         tags=["Analytics"],
         responses={
             200: {
                 "description": "Complete safety stock and coverage analysis",
                 "content": {
                     "application/json": {
                         "example": {
                             "sku_id": "UB-YTX14-BS",
                             "enhanced_demand": 1719.26,
                             "coverage_analysis": {
                                 "recommended_coverage_months": 6.3,
                                 "base_coverage_months": 6.0,
                                 "safety_stock_months": 0.2,
                                 "volatility_adjustment_months": 0.1
                             },
                             "safety_stock_details": {
                                 "safety_stock": 5.2,
                                 "z_score": 1.28,
                                 "service_level": 0.90
                             }
                         }
                     }
                 }
             },
             404: {"description": "SKU not found"}
         })
async def test_safety_stock_calculation(sku_id: str):
    """
    Test complete safety stock and coverage calculation system

    This endpoint demonstrates the integration of:
    - Weighted demand calculations
    - Demand volatility analysis
    - Statistical safety stock formulas
    - Volatility-based coverage adjustments

    Args:
        sku_id: SKU identifier to analyze

    Returns:
        Complete analysis with safety stock recommendations and coverage targets
    """
    try:
        # Initialize calculator
        calc = calculations.TransferCalculator()

        # Verify SKU exists and is active
        sku_query = """
        SELECT sku_id, description, abc_code, xyz_code, supplier, status
        FROM skus
        WHERE sku_id = %s AND status = 'Active'
        """

        sku_info = database.execute_query(sku_query, (sku_id,), fetch_one=True)

        if not sku_info:
            raise HTTPException(
                status_code=404,
                detail=f"SKU {sku_id} not found or inactive"
            )

        abc_class = sku_info['abc_code'] or 'C'
        xyz_class = sku_info['xyz_code'] or 'Z'
        supplier = sku_info['supplier']

        # Get enhanced demand calculation
        enhanced_result = calc.weighted_demand_calculator.get_enhanced_demand_calculation(
            sku_id, abc_class, xyz_class, 0, 0
        )

        enhanced_demand = enhanced_result['enhanced_demand']

        # Calculate coverage with safety stock
        coverage_result = calc.weighted_demand_calculator.calculate_coverage_with_safety_stock(
            sku_id, abc_class, enhanced_demand, supplier
        )

        # Test direct safety stock calculation
        volatility_metrics = calc.weighted_demand_calculator.calculate_demand_volatility(sku_id)
        weekly_demand = enhanced_demand / 4.33
        demand_std = volatility_metrics['standard_deviation'] / 4.33

        safety_stock_result = calc.weighted_demand_calculator.safety_stock_calculator.calculate_safety_stock(
            demand_std=demand_std,
            abc_class=abc_class,
            supplier=supplier,
            mean_demand=weekly_demand
        )

        # Calculate reorder point
        reorder_point_result = calc.weighted_demand_calculator.safety_stock_calculator.calculate_reorder_point(
            mean_demand=weekly_demand,
            demand_std=demand_std,
            abc_class=abc_class,
            supplier=supplier
        )

        # Get service level recommendations
        service_recommendations = calc.weighted_demand_calculator.safety_stock_calculator.get_service_level_recommendations(
            abc_class, volatility_metrics['volatility_class']
        )

        return {
            "sku_id": sku_id,
            "sku_info": {
                "description": sku_info['description'],
                "abc_code": abc_class,
                "xyz_code": xyz_class,
                "supplier": supplier,
                "status": sku_info['status']
            },
            "enhanced_demand": enhanced_demand,
            "enhanced_demand_details": enhanced_result,
            "coverage_analysis": coverage_result,
            "safety_stock_calculation": safety_stock_result,
            "reorder_point_calculation": reorder_point_result,
            "service_level_recommendations": service_recommendations,
            "volatility_metrics": volatility_metrics,
            "calculation_summary": {
                "recommended_coverage_months": coverage_result.get('recommended_coverage_months', 6.0),
                "safety_stock_units": safety_stock_result['safety_stock'],
                "reorder_point_units": reorder_point_result['reorder_point'],
                "service_level_target": service_recommendations['recommended_service_level'],
                "volatility_class": volatility_metrics['volatility_class'],
                "weekly_demand": round(weekly_demand, 2),
                "formula_used": safety_stock_result.get('formula', 'N/A')
            },
            "business_interpretation": {
                "coverage_recommendation": f"Stock {coverage_result.get('recommended_coverage_months', 6.0)} months of inventory",
                "safety_buffer": f"Keep {safety_stock_result['safety_stock']} units as safety stock",
                "reorder_trigger": f"Reorder when inventory drops to {reorder_point_result['reorder_point']} units",
                "risk_level": volatility_metrics['volatility_class'].title(),
                "confidence_level": f"{service_recommendations['recommended_service_level']*100:.1f}% service level"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Safety stock calculation test failed for {sku_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Safety stock calculation failed: {str(e)}"
        )

# ===================================================================
# CONFIGURATION MANAGEMENT API ENDPOINTS
# ===================================================================

@app.get("/api/config/settings",
         summary="Get All Configuration Settings",
         description="Retrieve all system configuration settings by category",
         tags=["Configuration"])
async def get_configuration_settings(category: Optional[str] = None):
    """
    Get all configuration settings with optional category filter

    Args:
        category: Optional category filter (lead_times, coverage, business_rules, etc.)

    Returns:
        Dictionary of configuration settings with metadata
    """
    try:
        config_data = settings.configuration_manager.get_all_settings(category)

        return {
            "success": True,
            "settings": config_data,
            "categories": list(set(s['category'] for s in config_data.values())),
            "total_settings": len(config_data)
        }

    except Exception as e:
        logger.error(f"Error retrieving configuration settings: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve configuration: {str(e)}"
        )

@app.get("/api/config/settings/{key}",
         summary="Get Configuration Setting",
         description="Retrieve a specific configuration setting by key",
         tags=["Configuration"])
async def get_configuration_setting(key: str):
    """Get specific configuration setting"""
    try:
        value = settings.configuration_manager.get_setting(key)

        if value is None:
            raise HTTPException(
                status_code=404,
                detail=f"Configuration key '{key}' not found"
            )

        # Get full setting info
        all_settings = settings.configuration_manager.get_all_settings()
        setting_info = all_settings.get(key, {})

        return {
            "key": key,
            "value": value,
            **setting_info
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting configuration setting {key}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get setting: {str(e)}"
        )

@app.put("/api/config/settings/{key}",
         summary="Update Configuration Setting",
         description="Update a system configuration setting",
         tags=["Configuration"])
async def update_configuration_setting(key: str, setting_data: settings.ConfigurationValue):
    """Update configuration setting"""
    try:
        success = settings.configuration_manager.set_setting(
            key=key,
            value=setting_data.value,
            data_type=setting_data.data_type,
            category=setting_data.category,
            description=setting_data.description
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to update configuration setting"
            )

        # Return updated value
        updated_value = settings.configuration_manager.get_setting(key)

        return {
            "success": True,
            "key": key,
            "value": updated_value,
            "message": f"Configuration '{key}' updated successfully"
        }

    except Exception as e:
        logger.error(f"Error updating configuration setting {key}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update setting: {str(e)}"
        )

@app.get("/api/config/supplier-lead-times",
         summary="Get Supplier Lead Time Overrides",
         description="Retrieve all supplier-specific lead time overrides",
         tags=["Configuration"])
async def get_supplier_lead_times():
    """Get all supplier lead time overrides"""
    try:
        lead_times = settings.configuration_manager.get_supplier_lead_times()

        return {
            "success": True,
            "supplier_lead_times": lead_times,
            "total_overrides": len(lead_times)
        }

    except Exception as e:
        logger.error(f"Error getting supplier lead times: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get supplier lead times: {str(e)}"
        )

@app.post("/api/config/supplier-lead-times",
          summary="Create Supplier Lead Time Override",
          description="Create or update supplier-specific lead time override",
          tags=["Configuration"])
async def create_supplier_lead_time(lead_time_data: settings.SupplierLeadTime):
    """Create or update supplier lead time override"""
    try:
        success = settings.configuration_manager.set_supplier_lead_time(
            supplier=lead_time_data.supplier,
            lead_time_days=lead_time_data.lead_time_days,
            destination=lead_time_data.destination,
            notes=lead_time_data.notes
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to create supplier lead time override"
            )

        return {
            "success": True,
            "supplier": lead_time_data.supplier,
            "lead_time_days": lead_time_data.lead_time_days,
            "destination": lead_time_data.destination,
            "message": f"Supplier lead time for '{lead_time_data.supplier}' updated successfully"
        }

    except Exception as e:
        logger.error(f"Error creating supplier lead time: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create supplier lead time: {str(e)}"
        )

@app.delete("/api/config/supplier-lead-times/{supplier}",
           summary="Delete Supplier Lead Time Override",
           description="Delete supplier-specific lead time override",
           tags=["Configuration"])
async def delete_supplier_lead_time(supplier: str, destination: Optional[str] = None):
    """Delete supplier lead time override"""
    try:
        success = settings.configuration_manager.delete_supplier_lead_time(
            supplier=supplier,
            destination=destination
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to delete supplier lead time override"
            )

        return {
            "success": True,
            "supplier": supplier,
            "destination": destination,
            "message": f"Supplier lead time override deleted successfully"
        }

    except Exception as e:
        logger.error(f"Error deleting supplier lead time: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete supplier lead time: {str(e)}"
        )

@app.get("/api/config/effective-lead-time",
         summary="Get Effective Lead Time",
         description="Get effective lead time considering supplier overrides",
         tags=["Configuration"])
async def get_effective_lead_time(supplier: Optional[str] = None, destination: Optional[str] = None):
    """Get effective lead time for supplier and destination"""
    try:
        lead_time = settings.configuration_manager.get_effective_lead_time(
            supplier=supplier,
            destination=destination
        )

        return {
            "supplier": supplier,
            "destination": destination,
            "effective_lead_time_days": lead_time,
            "source": "supplier_override" if supplier else "default_setting"
        }

    except Exception as e:
        logger.error(f"Error getting effective lead time: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get effective lead time: {str(e)}"
        )

@app.post("/api/config/reset",
          summary="Reset Configuration to Defaults",
          description="Reset configuration settings to default values",
          tags=["Configuration"])
async def reset_configuration(category: Optional[str] = None):
    """Reset configuration settings to defaults"""
    try:
        success = settings.configuration_manager.reset_to_defaults(category=category)

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to reset configuration"
            )

        return {
            "success": True,
            "category": category,
            "message": f"Configuration reset to defaults" + (f" for category '{category}'" if category else "")
        }

    except Exception as e:
        logger.error(f"Error resetting configuration: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset configuration: {str(e)}"
        )

# Cache Management API Endpoints
@app.post("/api/cache/refresh-weighted-demand",
          summary="Refresh Weighted Demand Cache",
          description="Refresh the weighted demand cache for all SKUs or a filtered subset",
          tags=["Cache Management"])
async def refresh_weighted_demand_cache(
    sku_filter: Optional[str] = None,
    force_refresh: bool = False
):
    """
    Refresh weighted demand cache to improve performance and prevent connection exhaustion

    This endpoint solves the database connection exhaustion issue by pre-calculating
    weighted demand values and storing them in the cache table.

    Args:
        sku_filter: Optional comma-separated list of SKU IDs to refresh (None = all SKUs)
        force_refresh: Force refresh even if cache is valid (default: False)

    Returns:
        Summary of cache refresh operation including timing and success metrics
    """
    try:
        logger.info("Cache refresh requested via API")

        # Parse SKU filter if provided
        sku_list = None
        if sku_filter:
            sku_list = [sku.strip() for sku in sku_filter.split(',') if sku.strip()]
            logger.info(f"Refreshing cache for {len(sku_list)} specific SKUs")

        # Create cache manager and perform refresh
        cache_manager = create_cache_manager()

        # Invalidate cache if force refresh is requested
        if force_refresh:
            cache_manager.invalidate_cache("API forced refresh")

        # Perform cache refresh
        summary = cache_manager.refresh_weighted_cache(
            sku_filter=sku_list,
            progress_callback=None  # Could add WebSocket progress updates later
        )

        # Add performance metrics
        summary['api_response'] = {
            'cache_refresh_completed': True,
            'timestamp': datetime.now().isoformat(),
            'sku_filter_applied': sku_list is not None,
            'force_refresh': force_refresh
        }

        # Return success response
        return {
            "success": True,
            "message": f"Cache refresh completed successfully",
            "summary": summary
        }

    except Exception as e:
        logger.error(f"Cache refresh failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Cache refresh failed: {str(e)}"
        )


@app.get("/api/cache/status",
         summary="Get Cache Status",
         description="Get current cache performance and status statistics",
         tags=["Cache Management"])
async def get_cache_status():
    """
    Get cache performance statistics and connection pool status

    Returns:
        Dictionary containing cache statistics, pool status, and performance metrics
    """
    try:
        cache_manager = create_cache_manager()

        # Get cache statistics
        cache_stats = cache_manager.get_cache_statistics()

        # Get connection pool status
        pool_status = database.get_connection_pool_status()

        return {
            "success": True,
            "cache_statistics": cache_stats,
            "connection_pool_status": pool_status,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to get cache status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get cache status: {str(e)}"
        )


@app.post("/api/cache/invalidate",
          summary="Invalidate Cache",
          description="Invalidate the entire weighted demand cache",
          tags=["Cache Management"])
async def invalidate_cache(reason: str = "Manual API invalidation"):
    """
    Invalidate the entire weighted demand cache

    This forces recalculation of all cached values on next access.
    Use when sales data has been imported or demand patterns have changed.

    Args:
        reason: Reason for cache invalidation (for logging)

    Returns:
        Success status and invalidation details
    """
    try:
        cache_manager = create_cache_manager()

        success = cache_manager.invalidate_cache(reason)

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Cache invalidation failed"
            )

        return {
            "success": True,
            "message": "Cache invalidated successfully",
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Cache invalidation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Cache invalidation failed: {str(e)}"
        )


@app.get("/api/cache/performance-test",
         summary="Test Cache Performance",
         description="Run a performance test on the connection pool",
         tags=["Cache Management"])
async def test_cache_performance(num_queries: int = 100):
    """
    Test connection pool performance with multiple queries

    Args:
        num_queries: Number of test queries to execute (default: 100)

    Returns:
        Performance test results including timing and success metrics
    """
    try:
        if num_queries > 1000:
            raise HTTPException(
                status_code=400,
                detail="Number of queries limited to 1000 for performance testing"
            )

        # Get connection pool and run performance test
        pool = database.get_connection_pool()
        if not pool:
            raise HTTPException(
                status_code=503,
                detail="Connection pool not available"
            )

        results = pool.test_pool_performance(num_queries)

        return {
            "success": True,
            "performance_results": results,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Performance test failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Performance test failed: {str(e)}"
        )

# =============================================================================
# TRANSFER CONFIRMATION ENDPOINTS
# =============================================================================

@app.get("/api/transfer-confirmations",
         summary="Get All Transfer Confirmations",
         description="Retrieve all confirmed transfer quantities with metadata",
         tags=["Transfer Confirmations"],
         responses={
             200: {"description": "List of all transfer confirmations"},
             500: {"description": "Database query failed"}
         })
async def get_all_transfer_confirmations():
    """
    Get all transfer confirmations with variance analysis

    Returns confirmed quantities, original suggestions, and variance percentages
    for all SKUs that have locked transfer quantities.

    Usage: Display confirmed quantities in transfer planning interface
    """
    try:
        from . import models
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        cursor.execute("""
            SELECT tc.sku_id, tc.confirmed_qty, tc.original_suggested_qty,
                   tc.confirmed_by, tc.confirmed_at, tc.notes,
                   s.description,
                   CASE
                       WHEN tc.original_suggested_qty > 0 THEN
                           ROUND(((tc.confirmed_qty - tc.original_suggested_qty) / tc.original_suggested_qty) * 100, 2)
                       ELSE 0
                   END as variance_percent
            FROM transfer_confirmations tc
            INNER JOIN skus s ON tc.sku_id = s.sku_id
            ORDER BY tc.confirmed_at DESC
        """)

        confirmations = cursor.fetchall()
        db.close()

        return {
            "confirmations": confirmations,
            "count": len(confirmations),
            "retrieved_at": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@app.get("/api/transfer-confirmations/{sku_id}",
         summary="Get Transfer Confirmation for SKU",
         description="Retrieve confirmation details for a specific SKU",
         tags=["Transfer Confirmations"],
         responses={
             200: {"description": "Transfer confirmation details"},
             404: {"description": "No confirmation found for this SKU"},
             500: {"description": "Database query failed"}
         })
async def get_transfer_confirmation(sku_id: str):
    """Get transfer confirmation for a specific SKU"""
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        cursor.execute("""
            SELECT tc.*, s.description,
                   CASE
                       WHEN tc.original_suggested_qty > 0 THEN
                           ROUND(((tc.confirmed_qty - tc.original_suggested_qty) / tc.original_suggested_qty) * 100, 2)
                       ELSE 0
                   END as variance_percent
            FROM transfer_confirmations tc
            INNER JOIN skus s ON tc.sku_id = s.sku_id
            WHERE tc.sku_id = %s
        """, (sku_id,))

        confirmation = cursor.fetchone()
        db.close()

        if not confirmation:
            raise HTTPException(status_code=404, detail=f"No confirmation found for SKU {sku_id}")

        return confirmation

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@app.post("/api/transfer-confirmations/{sku_id}",
          summary="Create/Update Transfer Confirmation",
          description="Lock in a transfer quantity for a specific SKU",
          tags=["Transfer Confirmations"],
          responses={
              200: {"description": "Confirmation created/updated successfully"},
              400: {"description": "Invalid input data"},
              404: {"description": "SKU not found"},
              500: {"description": "Database operation failed"}
          })
async def create_or_update_transfer_confirmation(
    sku_id: str,
    confirmation_data: dict = None
):
    """
    Create or update a transfer confirmation for a SKU

    Args:
        sku_id: SKU identifier
        confirmation_data: Dict containing confirmed_qty, original_suggested_qty, confirmed_by, notes

    Returns:
        dict: Confirmation details with success status
    """
    try:
        if not confirmation_data:
            raise HTTPException(status_code=400, detail="Confirmation data is required")

        confirmed_qty = confirmation_data.get('confirmed_qty')
        if confirmed_qty is None or confirmed_qty < 0:
            raise HTTPException(status_code=400, detail="confirmed_qty must be a non-negative integer")

        original_suggested_qty = confirmation_data.get('original_suggested_qty', 0)
        confirmed_by = confirmation_data.get('confirmed_by', 'system')
        notes = confirmation_data.get('notes', '')

        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        # Verify SKU exists
        cursor.execute("SELECT sku_id FROM skus WHERE sku_id = %s", (sku_id,))
        if not cursor.fetchone():
            db.close()
            raise HTTPException(status_code=404, detail=f"SKU {sku_id} not found")

        # Insert or update confirmation
        cursor.execute("""
            INSERT INTO transfer_confirmations
            (sku_id, confirmed_qty, original_suggested_qty, confirmed_by, notes)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            confirmed_qty = VALUES(confirmed_qty),
            confirmed_by = VALUES(confirmed_by),
            notes = VALUES(notes),
            confirmed_at = CURRENT_TIMESTAMP
        """, (sku_id, confirmed_qty, original_suggested_qty, confirmed_by, notes))

        db.commit()

        # Get the updated confirmation
        cursor.execute("""
            SELECT tc.*,
                   CASE
                       WHEN tc.original_suggested_qty > 0 THEN
                           ROUND(((tc.confirmed_qty - tc.original_suggested_qty) / tc.original_suggested_qty) * 100, 2)
                       ELSE 0
                   END as variance_percent
            FROM transfer_confirmations tc
            WHERE tc.sku_id = %s
        """, (sku_id,))

        result = cursor.fetchone()
        db.close()

        return {
            "success": True,
            "message": f"Transfer confirmation {'updated' if result else 'created'} for SKU {sku_id}",
            "confirmation": result
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database operation failed: {str(e)}")

@app.delete("/api/transfer-confirmations/{sku_id}",
            summary="Delete Transfer Confirmation",
            description="Remove confirmation lock for a specific SKU",
            tags=["Transfer Confirmations"],
            responses={
                200: {"description": "Confirmation deleted successfully"},
                404: {"description": "No confirmation found for this SKU"},
                500: {"description": "Database operation failed"}
            })
async def delete_transfer_confirmation(sku_id: str):
    """Remove transfer confirmation for a specific SKU"""
    try:
        db = database.get_database_connection()
        cursor = db.cursor()

        cursor.execute("DELETE FROM transfer_confirmations WHERE sku_id = %s", (sku_id,))
        rows_affected = cursor.rowcount

        db.commit()
        db.close()

        if rows_affected == 0:
            raise HTTPException(status_code=404, detail=f"No confirmation found for SKU {sku_id}")

        return {
            "success": True,
            "message": f"Transfer confirmation removed for SKU {sku_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database operation failed: {str(e)}")

@app.delete("/api/transfer-confirmations",
            summary="Clear All Transfer Confirmations",
            description="Remove all transfer confirmations",
            tags=["Transfer Confirmations"],
            responses={
                200: {"description": "All confirmations cleared successfully"},
                500: {"description": "Database operation failed"}
            })
async def clear_all_transfer_confirmations():
    """Clear all transfer confirmations"""
    try:
        db = database.get_database_connection()
        cursor = db.cursor()

        cursor.execute("DELETE FROM transfer_confirmations")
        rows_affected = cursor.rowcount

        db.commit()
        db.close()

        return {
            "success": True,
            "message": f"Cleared {rows_affected} transfer confirmations",
            "cleared_count": rows_affected
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database operation failed: {str(e)}")

@app.post("/api/transfer-confirmations/bulk",
          summary="Bulk Transfer Confirmations",
          description="Create or update multiple transfer confirmations at once",
          tags=["Transfer Confirmations"],
          responses={
              200: {"description": "Bulk confirmations processed successfully"},
              400: {"description": "Invalid input data"},
              500: {"description": "Database operation failed"}
          })
async def bulk_transfer_confirmations(bulk_data: dict):
    """
    Create or update multiple transfer confirmations

    Args:
        bulk_data: Dict containing 'confirmations' list and optional 'confirmed_by'

    Returns:
        dict: Summary of bulk operation results
    """
    try:
        confirmations = bulk_data.get('confirmations', [])
        confirmed_by = bulk_data.get('confirmed_by', 'system')

        if not confirmations:
            raise HTTPException(status_code=400, detail="No confirmations provided")

        db = database.get_database_connection()
        cursor = db.cursor()

        success_count = 0
        error_count = 0
        errors = []

        for conf in confirmations:
            try:
                sku_id = conf.get('sku_id')
                confirmed_qty = conf.get('confirmed_qty')
                original_suggested_qty = conf.get('original_suggested_qty', 0)
                notes = conf.get('notes', '')

                if not sku_id or confirmed_qty is None or confirmed_qty < 0:
                    raise ValueError("Invalid sku_id or confirmed_qty")

                cursor.execute("""
                    INSERT INTO transfer_confirmations
                    (sku_id, confirmed_qty, original_suggested_qty, confirmed_by, notes)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    confirmed_qty = VALUES(confirmed_qty),
                    confirmed_by = VALUES(confirmed_by),
                    notes = VALUES(notes),
                    confirmed_at = CURRENT_TIMESTAMP
                """, (sku_id, confirmed_qty, original_suggested_qty, confirmed_by, notes))

                success_count += 1

            except Exception as e:
                error_count += 1
                errors.append(f"SKU {sku_id}: {str(e)}")

        db.commit()
        db.close()

        return {
            "success": True,
            "message": f"Processed {len(confirmations)} confirmations",
            "success_count": success_count,
            "error_count": error_count,
            "errors": errors if errors else None
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bulk operation failed: {str(e)}")

@app.get("/api/export/confirmed-transfers",
         summary="Export Confirmed Transfers",
         description="Export only confirmed transfer quantities as CSV",
         tags=["Export", "Transfer Confirmations"],
         responses={
             200: {"description": "CSV file with confirmed transfers"},
             404: {"description": "No confirmed transfers found"},
             500: {"description": "Export generation failed"}
         })
async def export_confirmed_transfers():
    """Export only confirmed transfer quantities"""
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        cursor.execute("""
            SELECT tc.sku_id, s.description, tc.confirmed_qty,
                   tc.original_suggested_qty, tc.confirmed_by, tc.confirmed_at,
                   CASE
                       WHEN tc.original_suggested_qty > 0 THEN
                           ROUND(((tc.confirmed_qty - tc.original_suggested_qty) / tc.original_suggested_qty) * 100, 2)
                       ELSE 0
                   END as variance_percent
            FROM transfer_confirmations tc
            INNER JOIN skus s ON tc.sku_id = s.sku_id
            WHERE tc.confirmed_qty > 0
            ORDER BY tc.confirmed_at DESC
        """)

        confirmed_transfers = cursor.fetchall()
        db.close()

        if not confirmed_transfers:
            raise HTTPException(status_code=404, detail="No confirmed transfers found")

        # Generate CSV content
        csv_lines = [
            "SKU,Description,Confirmed Qty,Original Suggested,Variance %,Confirmed By,Confirmed At"
        ]

        for transfer in confirmed_transfers:
            csv_lines.append(
                f'"{transfer["sku_id"]}","{transfer["description"]}",{transfer["confirmed_qty"]},'
                f'{transfer["original_suggested_qty"]},{transfer["variance_percent"]},'
                f'"{transfer["confirmed_by"]}","{transfer["confirmed_at"]}"'
            )

        csv_content = "\n".join(csv_lines)

        # Return CSV file
        from fastapi.responses import Response
        filename = f"confirmed-transfers-{datetime.now().strftime('%Y%m%d')}.csv"

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export generation failed: {str(e)}")

# ===================================================================
# CA/KY Order Quantity Endpoints
# ===================================================================

@app.post("/api/order-quantities/{sku_id}",
          summary="Update CA/KY Order Quantities",
          description="Update manual order quantities for CA and KY warehouses",
          tags=["Order Management"],
          responses={
              200: {"description": "Order quantities updated successfully"},
              400: {"description": "Invalid input data"},
              500: {"description": "Database operation failed"}
          })
async def update_order_quantities(sku_id: str, order_data: dict):
    """
    Update CA and/or KY order quantities for a specific SKU

    Args:
        sku_id: SKU identifier
        order_data: Dict containing ca_order_qty and/or ky_order_qty

    Example request body:
        {
            "ca_order_qty": 100,
            "ky_order_qty": 50
        }
    """
    try:
        ca_order_qty = order_data.get('ca_order_qty')
        ky_order_qty = order_data.get('ky_order_qty')

        # Validate input
        if ca_order_qty is not None and (not isinstance(ca_order_qty, int) or ca_order_qty < 0):
            raise HTTPException(status_code=400, detail="ca_order_qty must be a non-negative integer")
        if ky_order_qty is not None and (not isinstance(ky_order_qty, int) or ky_order_qty < 0):
            raise HTTPException(status_code=400, detail="ky_order_qty must be a non-negative integer")

        if ca_order_qty is None and ky_order_qty is None:
            raise HTTPException(status_code=400, detail="At least one of ca_order_qty or ky_order_qty must be provided")

        db = database.get_database_connection()
        cursor = db.cursor()

        # Check if record exists
        cursor.execute("SELECT sku_id FROM transfer_confirmations WHERE sku_id = %s", (sku_id,))
        exists = cursor.fetchone()

        if exists:
            # Update existing record
            update_fields = []
            update_values = []

            if ca_order_qty is not None:
                update_fields.append("ca_order_qty = %s")
                update_values.append(ca_order_qty)
            if ky_order_qty is not None:
                update_fields.append("ky_order_qty = %s")
                update_values.append(ky_order_qty)

            update_values.append(sku_id)

            update_query = f"""
                UPDATE transfer_confirmations
                SET {', '.join(update_fields)}
                WHERE sku_id = %s
            """
            cursor.execute(update_query, update_values)
        else:
            # Create new record with default values
            cursor.execute("""
                INSERT INTO transfer_confirmations
                (sku_id, confirmed_qty, ca_order_qty, ky_order_qty)
                VALUES (%s, 0, %s, %s)
            """, (sku_id, ca_order_qty, ky_order_qty))

        db.commit()
        db.close()

        return {
            "message": "Order quantities updated successfully",
            "sku_id": sku_id,
            "ca_order_qty": ca_order_qty,
            "ky_order_qty": ky_order_qty
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database operation failed: {str(e)}")

@app.get("/api/order-quantities/{sku_id}",
         summary="Get CA/KY Order Quantities",
         description="Retrieve manual order quantities for a specific SKU",
         tags=["Order Management"],
         responses={
             200: {"description": "Order quantities retrieved successfully"},
             404: {"description": "SKU not found"},
             500: {"description": "Database query failed"}
         })
async def get_order_quantities(sku_id: str):
    """
    Get CA and KY order quantities for a specific SKU

    Args:
        sku_id: SKU identifier
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        cursor.execute("""
            SELECT sku_id, ca_order_qty, ky_order_qty
            FROM transfer_confirmations
            WHERE sku_id = %s
        """, (sku_id,))

        result = cursor.fetchone()
        db.close()

        if not result:
            return {
                "sku_id": sku_id,
                "ca_order_qty": None,
                "ky_order_qty": None
            }

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

@app.delete("/api/order-quantities/{sku_id}",
            summary="Clear CA/KY Order Quantities",
            description="Clear manual order quantities for a specific SKU",
            tags=["Order Management"],
            responses={
                200: {"description": "Order quantities cleared successfully"},
                500: {"description": "Database operation failed"}
            })
async def clear_order_quantities(sku_id: str):
    """
    Clear CA and KY order quantities for a specific SKU

    Args:
        sku_id: SKU identifier
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor()

        cursor.execute("""
            UPDATE transfer_confirmations
            SET ca_order_qty = NULL, ky_order_qty = NULL
            WHERE sku_id = %s
        """, (sku_id,))

        rows_affected = cursor.rowcount
        db.commit()
        db.close()

        return {
            "message": "Order quantities cleared successfully",
            "sku_id": sku_id,
            "rows_affected": rows_affected
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database operation failed: {str(e)}")

# =============================================================================
# SUPPLIER ANALYTICS API ENDPOINTS
# =============================================================================
# Purpose: Standalone supplier lead time analytics system
# Features: Historical shipment import, performance metrics, reliability scoring
# Business Logic: Statistical analysis, P95 calculations, performance alerts

# Import supplier analytics modules
try:
    from . import supplier_analytics
    from . import supplier_import
except ImportError:
    import supplier_analytics
    import supplier_import

@app.post("/api/supplier/shipments/import",
         summary="Import Supplier Shipment History",
         description="Upload CSV file with historical supplier shipment data",
         tags=["Supplier Analytics"],
         responses={
             200: {"description": "Import completed with results"},
             400: {"description": "Invalid CSV format or validation errors"},
             500: {"description": "Import processing failed"}
         })
async def import_supplier_shipments(
    file: UploadFile = File(..., description="CSV file with shipment history"),
    uploaded_by: str = Form("system", description="Username of uploader")
):
    """
    Import historical supplier shipment data from CSV file

    Expected CSV Format:
    - po_number: Unique purchase order number
    - supplier: Supplier name (will be normalized)
    - order_date: Date order was placed (YYYY-MM-DD format)
    - received_date: Date order was received (YYYY-MM-DD format)
    - destination: 'burnaby' or 'kentucky'
    - was_partial: Optional boolean (true/false)
    - notes: Optional text notes

    Business Logic:
    - Validates all data before importing
    - Normalizes supplier names for consistency
    - Calculates lead times automatically
    - Handles duplicate PO numbers with updates
    - Provides detailed error reporting

    Args:
        file: CSV file upload
        uploaded_by: Username for audit trail

    Returns:
        Dict with import results, statistics, and any errors

    Raises:
        HTTPException: 400 for validation errors, 500 for processing errors
    """
    try:
        # Validate file type
        if not file.filename.lower().endswith('.csv'):
            raise HTTPException(status_code=400, detail="File must be a CSV file")

        # Read file content
        content = await file.read()
        csv_content = content.decode('utf-8-sig')  # Handle BOM if present

        # Import using supplier importer
        importer = supplier_import.get_supplier_importer()
        result = importer.import_csv_data(csv_content, uploaded_by)

        logger.info(f"Supplier shipment import completed: {result['imported_records']} records imported")
        return result

    except supplier_import.SupplierImportError as e:
        logger.error(f"Supplier import validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Supplier import processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Import processing failed: {str(e)}")

@app.post("/api/supplier/metrics/calculate",
         summary="Calculate Supplier Performance Metrics",
         description="Calculate or recalculate performance metrics for all suppliers",
         tags=["Supplier Analytics"],
         responses={
             200: {"description": "Metrics calculated successfully"},
             500: {"description": "Calculation failed"}
         })
async def calculate_supplier_metrics(
    period_months: int = Form(12, description="Analysis period in months (6, 12, 24, or 0 for all time)"),
    supplier: Optional[str] = Form(None, description="Specific supplier name (leave empty for all)")
):
    """
    Calculate comprehensive performance metrics for suppliers

    Calculates statistical lead time metrics including:
    - Average, median, and P95 lead times
    - Min/max delivery times
    - Standard deviation and coefficient of variation
    - Reliability scores (0-100)
    - Destination-specific breakdowns

    Business Logic:
    - Uses P95 as primary planning metric
    - Applies confidence factors based on sample size
    - Updates cache table for dashboard performance
    - Generates planning recommendations

    Args:
        period_months: Analysis time period (6, 12, 24, or 0 for all)
        supplier: Optional specific supplier (None for all)

    Returns:
        Dict with calculation results and statistics

    Raises:
        HTTPException: 500 if calculation fails
    """
    try:
        analytics = supplier_analytics.get_supplier_analytics()
        result = analytics.update_supplier_metrics_cache(supplier, period_months)

        logger.info(f"Supplier metrics calculated: {result['updated_count']} suppliers updated")
        return {
            "success": True,
            "message": f"Metrics calculated for {result['updated_count']} suppliers",
            "stats": result
        }

    except Exception as e:
        logger.error(f"Supplier metrics calculation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Calculation failed: {str(e)}")

@app.get("/api/supplier/metrics",
         summary="Get All Supplier Metrics",
         description="Retrieve performance metrics for all suppliers",
         tags=["Supplier Analytics"],
         responses={
             200: {"description": "List of supplier metrics"},
             500: {"description": "Database query failed"}
         })
async def get_all_supplier_metrics(
    period_months: int = 12,
    min_shipments: int = 1
):
    """
    Retrieve performance metrics for all suppliers

    Returns comprehensive metrics including reliability scores,
    lead time statistics, and planning recommendations.

    Args:
        period_months: Analysis period (6, 12, 24, or 0)
        min_shipments: Minimum shipments required to include supplier

    Returns:
        Dict with supplier metrics list and summary statistics

    Raises:
        HTTPException: 500 if database query fails
    """
    try:
        analytics = supplier_analytics.get_supplier_analytics()
        metrics_list = analytics.calculate_all_supplier_metrics(period_months)

        # Filter by minimum shipments
        filtered_metrics = [m for m in metrics_list if m.get('shipment_count', 0) >= min_shipments]

        # Calculate summary statistics
        if filtered_metrics:
            avg_reliability = sum(m.get('reliability_score', 0) for m in filtered_metrics) / len(filtered_metrics)
            avg_lead_time = sum(m.get('avg_lead_time', 0) for m in filtered_metrics) / len(filtered_metrics)
        else:
            avg_reliability = 0
            avg_lead_time = 0

        return {
            "suppliers": filtered_metrics,
            "count": len(filtered_metrics),
            "summary": {
                "avg_reliability_score": round(avg_reliability, 1),
                "avg_lead_time": round(avg_lead_time, 1),
                "analysis_period": f"{period_months}_months" if period_months > 0 else "all_time"
            }
        }

    except Exception as e:
        logger.error(f"Error retrieving supplier metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

@app.get("/api/supplier/metrics/{supplier}",
         summary="Get Detailed Supplier Metrics",
         description="Retrieve comprehensive analytics for a specific supplier",
         tags=["Supplier Analytics"],
         responses={
             200: {"description": "Detailed supplier metrics"},
             404: {"description": "Supplier not found"},
             500: {"description": "Database query failed"}
         })
async def get_supplier_detailed_metrics(
    supplier: str,
    period_months: int = 12
):
    """
    Retrieve detailed performance analytics for a specific supplier

    Provides comprehensive analysis including:
    - Statistical metrics and reliability scoring
    - Destination-specific performance breakdown
    - Performance trends and recommendations
    - Recent shipment history

    Args:
        supplier: Supplier name
        period_months: Analysis period

    Returns:
        Dict with detailed supplier analytics

    Raises:
        HTTPException: 404 if supplier not found, 500 for database errors
    """
    try:
        analytics = supplier_analytics.get_supplier_analytics()
        metrics = analytics.calculate_supplier_metrics(supplier, period_months)

        if metrics.get('error'):
            raise HTTPException(status_code=404, detail=f"No shipment data found for supplier: {supplier}")

        # Get recent shipments for context
        connection = database.get_database_connection()
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT po_number, order_date, received_date, actual_lead_time, destination
                FROM supplier_shipments
                WHERE UPPER(TRIM(supplier)) = %s
                ORDER BY received_date DESC
                LIMIT 10
            """, (supplier.strip().upper(),))
            recent_shipments = cursor.fetchall()

        metrics['recent_shipments'] = recent_shipments
        return metrics

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving detailed metrics for {supplier}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

@app.get("/api/supplier/metrics/export",
         summary="Export Supplier Metrics",
         description="Export supplier performance metrics in CSV or JSON format",
         tags=["Supplier Analytics"],
         responses={
             200: {"description": "Exported metrics file"},
             500: {"description": "Export failed"}
         })
async def export_supplier_metrics(
    format: str = "csv",
    period_months: int = 12
):
    """
    Export supplier performance metrics for external use

    Supports CSV and JSON formats for integration with other systems
    or for supplier performance reviews.

    Args:
        format: Export format ('csv' or 'json')
        period_months: Analysis period

    Returns:
        File download with supplier metrics

    Raises:
        HTTPException: 400 for invalid format, 500 for export errors
    """
    try:
        if format not in ['csv', 'json']:
            raise HTTPException(status_code=400, detail="Format must be 'csv' or 'json'")

        analytics = supplier_analytics.get_supplier_analytics()
        metrics_list = analytics.calculate_all_supplier_metrics(period_months)

        if format == 'csv':
            # Generate CSV content
            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow([
                'Supplier', 'Avg Lead Time', 'P95 Lead Time', 'Reliability Score',
                'Shipment Count', 'Min Lead Time', 'Max Lead Time', 'Std Deviation',
                'Coefficient Variation', 'Recommendation'
            ])

            # Write data rows
            for metrics in metrics_list:
                writer.writerow([
                    metrics.get('supplier', ''),
                    metrics.get('avg_lead_time', ''),
                    metrics.get('p95_lead_time', ''),
                    metrics.get('reliability_score', ''),
                    metrics.get('shipment_count', ''),
                    metrics.get('min_lead_time', ''),
                    metrics.get('max_lead_time', ''),
                    metrics.get('std_dev_lead_time', ''),
                    metrics.get('coefficient_variation', ''),
                    metrics.get('recommendation', '')
                ])

            csv_content = output.getvalue()
            output.close()

            return StreamingResponse(
                io.BytesIO(csv_content.encode('utf-8')),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=supplier_metrics_{period_months}m.csv"}
            )

        else:  # JSON format
            import json
            json_content = json.dumps({
                'suppliers': metrics_list,
                'analysis_period': f"{period_months}_months" if period_months > 0 else "all_time",
                'generated_at': datetime.now().isoformat()
            }, indent=2, default=str)

            return StreamingResponse(
                io.BytesIO(json_content.encode('utf-8')),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename=supplier_metrics_{period_months}m.json"}
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting supplier metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

@app.get("/api/supplier/alerts",
         summary="Get Supplier Performance Alerts",
         description="Retrieve performance degradation and reliability alerts",
         tags=["Supplier Analytics"],
         responses={
             200: {"description": "List of performance alerts"},
             500: {"description": "Alert detection failed"}
         })
async def get_supplier_alerts(
    supplier: Optional[str] = None,
    severity: Optional[str] = None
):
    """
    Detect and retrieve supplier performance alerts

    Identifies issues such as:
    - Performance degradation (>15% increase in lead time)
    - High variability warnings (CV > 25%)
    - Insufficient data warnings (<5 shipments)
    - Outlier detection (shipments >2x normal)

    Args:
        supplier: Optional specific supplier filter
        severity: Optional severity filter ('HIGH', 'MEDIUM', 'LOW')

    Returns:
        Dict with alerts list and summary statistics

    Raises:
        HTTPException: 500 if alert detection fails
    """
    try:
        analytics = supplier_analytics.get_supplier_analytics()
        alerts = analytics.detect_performance_alerts(supplier)

        # Filter by severity if specified
        if severity:
            severity_upper = severity.upper()
            if severity_upper in ['HIGH', 'MEDIUM', 'LOW']:
                alerts = [alert for alert in alerts if alert.get('severity') == severity_upper]

        # Summary statistics
        alert_counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        for alert in alerts:
            severity_level = alert.get('severity', 'LOW')
            if severity_level in alert_counts:
                alert_counts[severity_level] += 1

        return {
            "alerts": alerts,
            "count": len(alerts),
            "summary": alert_counts
        }

    except Exception as e:
        logger.error(f"Error detecting supplier alerts: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Alert detection failed: {str(e)}")

@app.get("/api/supplier/{supplier}/seasonal-analysis",
         summary="Get Supplier Seasonal Pattern Analysis",
         description="Analyze seasonal patterns in supplier lead time performance",
         tags=["Supplier Analytics"],
         responses={
             200: {"description": "Seasonal pattern analysis results"},
             404: {"description": "Supplier not found"},
             500: {"description": "Analysis failed"}
         })
async def get_supplier_seasonal_analysis(supplier: str):
    """
    Analyze seasonal patterns in supplier lead time performance

    Provides comprehensive seasonal analysis including:
    - Monthly average lead times
    - Peak and best performing months
    - Seasonality strength scoring
    - Business insights and recommendations

    Args:
        supplier: Supplier name to analyze

    Returns:
        Dict with seasonal pattern analysis and recommendations

    Raises:
        HTTPException: 404 if supplier not found, 500 if analysis fails
    """
    try:
        analytics = supplier_analytics.get_supplier_analytics()
        seasonal_data = analytics.detect_seasonal_patterns(supplier)

        if not seasonal_data.get('sufficient_data'):
            raise HTTPException(
                status_code=404,
                detail=f"Insufficient data for seasonal analysis of supplier: {supplier}"
            )

        return {
            "supplier": supplier,
            "seasonal_analysis": seasonal_data,
            "generated_at": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing seasonal patterns for {supplier}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Seasonal analysis failed: {str(e)}")

@app.get("/api/supplier/{supplier}/performance-trends",
         summary="Get Supplier Performance Trend Analysis",
         description="Analyze supplier performance trends over time",
         tags=["Supplier Analytics"],
         responses={
             200: {"description": "Performance trend analysis results"},
             404: {"description": "Supplier not found"},
             500: {"description": "Analysis failed"}
         })
async def get_supplier_performance_trends(
    supplier: str,
    periods: int = 6
):
    """
    Analyze supplier performance trends over multiple time periods

    Provides trend analysis including:
    - Performance direction (improving/declining/stable)
    - Trend strength and statistical significance
    - Quarterly performance data
    - Performance forecasting
    - Actionable business recommendations

    Args:
        supplier: Supplier name to analyze
        periods: Number of quarters to analyze (default: 6)

    Returns:
        Dict with trend analysis and performance forecast

    Raises:
        HTTPException: 404 if supplier not found, 500 if analysis fails
    """
    try:
        analytics = supplier_analytics.get_supplier_analytics()
        trend_data = analytics.calculate_performance_trends(supplier, periods)

        if not trend_data.get('sufficient_data'):
            raise HTTPException(
                status_code=404,
                detail=f"Insufficient data for trend analysis of supplier: {supplier}"
            )

        return {
            "supplier": supplier,
            "trend_analysis": trend_data,
            "analysis_periods": periods,
            "generated_at": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing performance trends for {supplier}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Trend analysis failed: {str(e)}")

# ===================================================================
# Supplier Name Mapping API Endpoints
# ===================================================================

@app.get("/api/suppliers",
         summary="List All Suppliers",
         description="Get all suppliers from the master table for dropdown selection",
         tags=["Supplier Management"],
         responses={
             200: {"description": "List of suppliers retrieved successfully"},
             500: {"description": "Failed to retrieve suppliers"}
         })
async def get_all_suppliers(active_only: bool = True):
    """
    Retrieve all suppliers for dropdown selection and mapping interfaces

    Provides a complete list of suppliers from the master table, optionally
    filtered to show only active suppliers. Used in mapping modals and
    supplier selection dropdowns.

    Args:
        active_only: Whether to return only active suppliers (default: True)

    Returns:
        Dict containing list of suppliers with id, display_name, and status

    Example Response:
        {
            "suppliers": [
                {
                    "id": 1,
                    "display_name": "ABC Corporation",
                    "normalized_name": "abc corporation",
                    "is_active": true
                }
            ],
            "total_count": 150,
            "active_count": 148
        }
    """
    try:
        matcher = supplier_matcher.get_supplier_matcher()
        suppliers = matcher.get_all_suppliers(active_only=active_only)

        # Get total counts
        all_suppliers = matcher.get_all_suppliers(active_only=False) if active_only else suppliers
        active_suppliers = [s for s in all_suppliers if s.get('is_active', True)]

        return {
            "suppliers": suppliers,
            "total_count": len(all_suppliers),
            "active_count": len(active_suppliers),
            "filtered_count": len(suppliers)
        }

    except Exception as e:
        logger.error(f"Error retrieving suppliers: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve suppliers: {str(e)}")

@app.post("/api/suppliers",
          summary="Create New Supplier",
          description="Create a new supplier in the master table",
          tags=["Supplier Management"],
          responses={
              201: {"description": "Supplier created successfully"},
              400: {"description": "Invalid supplier data"},
              409: {"description": "Supplier already exists"},
              500: {"description": "Failed to create supplier"}
          })
async def create_supplier(supplier_data: dict):
    """
    Create a new supplier in the master table

    Creates a new supplier with name normalization and validation.
    Prevents duplicate suppliers by checking normalized names.

    Args:
        supplier_data: Dict containing supplier information:
            - display_name (required): Display name for the supplier
            - legal_name (optional): Legal business name
            - supplier_code (optional): Internal supplier code
            - created_by (optional): Username creating the supplier

    Returns:
        Dict with new supplier information including assigned ID

    Raises:
        HTTPException: 400 if data invalid, 409 if duplicate, 500 if creation fails
    """
    try:
        # Validate required fields
        if not supplier_data.get('display_name'):
            raise HTTPException(status_code=400, detail="Display name is required")

        matcher = supplier_matcher.get_supplier_matcher()

        supplier_id = matcher.create_supplier(
            display_name=supplier_data['display_name'],
            legal_name=supplier_data.get('legal_name'),
            supplier_code=supplier_data.get('supplier_code'),
            created_by=supplier_data.get('created_by', 'api_user')
        )

        # Get the created supplier details
        suppliers = matcher.get_all_suppliers(active_only=False)
        created_supplier = next((s for s in suppliers if s['id'] == supplier_id), None)

        return {
            "success": True,
            "supplier_id": supplier_id,
            "supplier": created_supplier,
            "message": f"Supplier '{supplier_data['display_name']}' created successfully"
        }

    except supplier_matcher.SupplierMatchError as e:
        if "already exists" in str(e).lower():
            raise HTTPException(status_code=409, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating supplier: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create supplier: {str(e)}")

@app.post("/api/supplier/match",
          summary="Find Supplier Matches",
          description="Find potential matches for supplier names using fuzzy matching",
          tags=["Supplier Management"],
          responses={
              200: {"description": "Matches found and returned"},
              400: {"description": "Invalid supplier name"},
              500: {"description": "Matching failed"}
          })
async def find_supplier_matches(match_request: dict):
    """
    Find potential matches for supplier names using intelligent matching

    Uses fuzzy matching algorithms to find existing suppliers that might
    match the provided name. Returns results sorted by confidence score.

    Args:
        match_request: Dict containing:
            - supplier_name (required): Name to find matches for
            - limit (optional): Maximum matches to return (default: 5)
            - min_confidence (optional): Minimum confidence threshold

    Returns:
        Dict containing array of matches with confidence scores and match types

    Example Request:
        {
            "supplier_name": "ABC Corp",
            "limit": 5,
            "min_confidence": 70
        }

    Example Response:
        {
            "matches": [
                {
                    "supplier_id": 123,
                    "display_name": "ABC Corporation",
                    "confidence": 95.5,
                    "match_type": "fuzzy",
                    "normalized_name": "abc corporation"
                }
            ],
            "original_name": "ABC Corp",
            "total_matches": 1
        }
    """
    try:
        supplier_name = match_request.get('supplier_name')
        if not supplier_name:
            raise HTTPException(status_code=400, detail="Supplier name is required")

        limit = match_request.get('limit', 5)
        if limit < 1 or limit > 20:
            raise HTTPException(status_code=400, detail="Limit must be between 1 and 20")

        matcher = supplier_matcher.get_supplier_matcher()

        # Set minimum confidence if provided
        if 'min_confidence' in match_request:
            matcher.min_confidence_threshold = float(match_request['min_confidence'])

        matches = matcher.find_matches(supplier_name, limit=limit)

        return {
            "matches": matches,
            "original_name": supplier_name,
            "normalized_name": matcher.normalize_supplier_name(supplier_name),
            "total_matches": len(matches)
        }

    except Exception as e:
        logger.error(f"Error finding matches for '{match_request.get('supplier_name', 'unknown')}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Matching failed: {str(e)}")

@app.post("/api/supplier/aliases",
          summary="Save Supplier Name Mapping",
          description="Save a user-confirmed mapping as an alias for future reference",
          tags=["Supplier Management"],
          responses={
              200: {"description": "Alias saved successfully"},
              400: {"description": "Invalid mapping data"},
              500: {"description": "Failed to save alias"}
          })
async def save_supplier_alias(alias_data: dict):
    """
    Save a user-confirmed supplier name mapping as an alias

    When users manually map supplier names during import, this saves the mapping
    as an alias so the system can auto-match similar names in the future.

    Args:
        alias_data: Dict containing:
            - original_name (required): The original name that was mapped
            - supplier_id (required): The supplier ID it was mapped to
            - confidence (optional): Confidence score for the mapping
            - created_by (optional): Username who created the mapping

    Returns:
        Dict confirming the alias was saved

    Example Request:
        {
            "original_name": "ABC Corp",
            "supplier_id": 123,
            "confidence": 100.0,
            "created_by": "john_doe"
        }
    """
    try:
        # Validate required fields
        original_name = alias_data.get('original_name')
        supplier_id = alias_data.get('supplier_id')

        if not original_name:
            raise HTTPException(status_code=400, detail="Original name is required")
        if not supplier_id:
            raise HTTPException(status_code=400, detail="Supplier ID is required")

        matcher = supplier_matcher.get_supplier_matcher()

        success = matcher.save_mapping(
            original_name=original_name,
            supplier_id=int(supplier_id),
            confidence=float(alias_data.get('confidence', 100.0)),
            created_by=alias_data.get('created_by', 'api_user')
        )

        return {
            "success": success,
            "message": f"Mapping saved: '{original_name}' -> supplier_id {supplier_id}",
            "original_name": original_name,
            "supplier_id": supplier_id
        }

    except Exception as e:
        logger.error(f"Error saving alias: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save alias: {str(e)}")

@app.post("/api/supplier/import/preview",
          summary="Preview Supplier Import with Mapping",
          description="Analyze CSV supplier names and provide mapping suggestions",
          tags=["Supplier Management"],
          responses={
              200: {"description": "Import preview generated successfully"},
              400: {"description": "Invalid CSV data"},
              500: {"description": "Preview generation failed"}
          })
async def preview_supplier_import(file: UploadFile = File(...)):
    """
    Analyze CSV file and provide supplier name mapping suggestions

    Extracts unique supplier names from CSV, finds potential matches,
    and returns mapping suggestions for user confirmation before import.

    Args:
        file: CSV file containing supplier data

    Returns:
        Dict containing:
            - unique_suppliers: List of unique supplier names found
            - mapping_suggestions: Suggested matches for each supplier
            - total_suppliers: Count of unique suppliers
            - estimated_new_suppliers: Count needing manual mapping

    Example Response:
        {
            "unique_suppliers": ["ABC Corp", "XYZ Ltd"],
            "mapping_suggestions": {
                "ABC Corp": [
                    {
                        "supplier_id": 123,
                        "display_name": "ABC Corporation",
                        "confidence": 95.5,
                        "match_type": "fuzzy"
                    }
                ]
            },
            "total_suppliers": 2,
            "estimated_new_suppliers": 1
        }
    """
    try:
        # Read CSV content
        content = await file.read()
        csv_content = content.decode('utf-8')

        # Extract unique supplier names from CSV
        import io
        import csv
        csv_file = io.StringIO(csv_content)
        csv_reader = csv.DictReader(csv_file)

        # Find supplier column (case-insensitive)
        supplier_column = None
        for fieldname in csv_reader.fieldnames or []:
            if fieldname.lower().strip() in ['supplier', 'supplier_name', 'vendor', 'vendor_name']:
                supplier_column = fieldname
                break

        if not supplier_column:
            raise HTTPException(
                status_code=400,
                detail="CSV must contain a 'supplier' or 'supplier_name' column"
            )

        # Extract unique supplier names
        unique_suppliers = set()
        for row in csv_reader:
            supplier_name = row.get(supplier_column, '').strip()
            if supplier_name and supplier_name.lower() not in ['n/a', 'na', 'none', 'null', '']:
                unique_suppliers.add(supplier_name)

        # Get mapping suggestions for each supplier
        matcher = supplier_matcher.get_supplier_matcher()

        mapping_suggestions = {}
        estimated_new_suppliers = 0

        for supplier_name in unique_suppliers:
            matches = matcher.find_matches(supplier_name, limit=3)
            mapping_suggestions[supplier_name] = matches

            # Count as new if no high-confidence matches
            high_confidence_matches = [m for m in matches if m['confidence'] >= 90]
            if not high_confidence_matches:
                estimated_new_suppliers += 1

        return {
            "unique_suppliers": sorted(list(unique_suppliers)),
            "mapping_suggestions": mapping_suggestions,
            "total_suppliers": len(unique_suppliers),
            "estimated_new_suppliers": estimated_new_suppliers,
            "csv_column_used": supplier_column
        }

    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Invalid CSV file encoding. Please use UTF-8.")
    except Exception as e:
        logger.error(f"Error previewing supplier import: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")

# Serve the main dashboard
@app.get("/dashboard")
async def dashboard_redirect():
    """Redirect to the main dashboard"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")

# Serve the frontend dashboard (legacy)
@app.get("/dashboard-legacy", response_class=HTMLResponse)
async def dashboard_legacy():
    """Serve the main dashboard page"""
    # In a real implementation, we'd serve the actual HTML file
    return """
    <html>
        <head>
            <title>Warehouse Transfer Planning Tool</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
                .container { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                h1 { color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }
                .alert { padding: 15px; margin: 10px 0; border-radius: 4px; }
                .alert-info { background: #d1ecf1; border: 1px solid #bee5eb; color: #0c5460; }
                .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }
                .metric { background: #f8f9fa; padding: 20px; border-radius: 6px; text-align: center; border-left: 4px solid #007bff; }
                .metric h3 { margin: 0 0 10px 0; color: #666; font-size: 14px; }
                .metric .value { font-size: 24px; font-weight: bold; color: #333; }
                .api-links { margin: 30px 0; }
                .api-links a { display: inline-block; margin: 5px 10px 5px 0; padding: 8px 16px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; }
                .api-links a:hover { background: #0056b3; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Warehouse Transfer Planning Tool</h1>
                
                <div class="alert alert-info">
                    <strong>Status:</strong> Application is running successfully! Database connection verified.
                </div>
                
                <div class="metrics">
                    <div class="metric">
                        <h3>Database Status</h3>
                        <div class="value">✅ Connected</div>
                    </div>
                    <div class="metric">
                        <h3>API Status</h3>
                        <div class="value">✅ Active</div>
                    </div>
                    <div class="metric">
                        <h3>Version</h3>
                        <div class="value">v1.0.0</div>
                    </div>
                </div>
                
                <div class="api-links">
                    <h3>API Endpoints:</h3>
                    <a href="/api/docs" target="_blank">API Documentation</a>
                    <a href="/api/dashboard" target="_blank">Dashboard Metrics</a>
                    <a href="/api/skus" target="_blank">SKU Data</a>
                    <a href="/api/transfer-recommendations" target="_blank">Transfer Recommendations</a>
                    <a href="/health" target="_blank">Health Check</a>
                </div>
                
                <p><strong>Next Steps:</strong></p>
                <ul>
                    <li>✅ Database setup completed with sample data</li>
                    <li>✅ Basic API endpoints working</li>
                    <li>⏳ Frontend development in progress</li>
                    <li>⏳ Stockout correction algorithms</li>
                    <li>⏳ Excel import/export functionality</li>
                </ul>
            </div>
        </body>
    </html>
    """


# V9.0: Monthly Supplier Order Background Scheduler
# Startup and shutdown event handlers for background jobs
@app.on_event("startup")
async def startup_event():
    """
    Application startup tasks.
    Start the monthly supplier order recommendation scheduler.
    """
    try:
        from backend.background_scheduler import start_scheduler
        start_scheduler()
        logger.info("Background schedulers started successfully")
    except ImportError as e:
        logger.warning(f"Background scheduler module not available: {e}")
    except Exception as e:
        logger.error(f"Error starting background schedulers: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """
    Application shutdown tasks.
    Stop the monthly supplier order recommendation scheduler gracefully.
    """
    try:
        from backend.background_scheduler import stop_scheduler
        stop_scheduler()
        logger.info("Background schedulers stopped successfully")
    except Exception as e:
        logger.error(f"Error stopping background schedulers: {e}")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)