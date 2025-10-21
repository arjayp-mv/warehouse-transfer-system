# Claude Code Best Practices for High-Performance Applications

## 🎯 Purpose
This document contains proven patterns for building fast, maintainable applications with Claude Code, specifically for projects handling large datasets (100K+ records).

---

## 🚨 CRITICAL PERFORMANCE RULES

### Rule #1: NEVER Calculate on Page Load

**❌ WRONG - Causes 30-minute load times:**
```python
@app.get("/listings")
def get_listings():
    listings = db.query(Listing).all()  # Load 100K records

    for listing in listings:
        # Calculating metrics on every page load
        listing.revenue_30d = calculate_revenue(listing)
        listing.profit_margin = calculate_profit(listing)
        listing.roi = calculate_roi(listing)

    return listings
```

**✅ CORRECT - Loads in < 1 second:**
```python
# Background job runs every 30 minutes
@scheduler.scheduled_job('interval', minutes=30)
def pre_calculate_metrics():
    # Calculate and store in database
    for listing in get_batch(100):
        metrics = calculate_all_metrics(listing)
        db.save_to_calculated_metrics_table(metrics)

@app.get("/listings")
def get_listings():
    # Just fetch pre-calculated data
    return db.query("SELECT * FROM calculated_metrics LIMIT 50")
```

**Key Principle:** If it takes > 1 second to calculate, do it in the background and cache the result.

---

### Rule #2: Always Use Pagination

**❌ WRONG - Returns all data:**
```python
@app.get("/products")
def get_products():
    return db.query(Product).all()  # Returns 100K records
```

**✅ CORRECT - Returns max 50 items:**
```python
@app.get("/products")
def get_products(page: int = 1, page_size: int = 50):
    # Enforce maximum
    page_size = min(page_size, 100)

    offset = (page - 1) * page_size
    total = db.query(Product).count()
    items = db.query(Product).offset(offset).limit(page_size).all()

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size
    }
```

**Maximum Limits:**
- Initial page load: 25-50 items
- Acceptable: 50-100 items
- Never exceed: 100 items per request

---

### Rule #3: Database Aggregation Over Python Loops

**❌ WRONG - Slow N+1 query problem:**
```python
# Fetch projects with eager loading
projects = db.query(Project).options(joinedload(Project.subprojects)).all()

# Calculate stats in Python (SLOW)
for project in projects:
    project.total_keywords = sum(sub.keyword_count for sub in project.subprojects)
    project.subproject_count = len(project.subprojects)
```

**✅ CORRECT - Fast batched SQL aggregation:**
```python
# Fetch only the projects for current page
project_ids = [p.id for p in projects]

# Single batched query for subproject counts
subproject_counts = dict(
    db.query(Subproject.project_id, func.count(Subproject.id))
      .filter(Subproject.project_id.in_(project_ids))
      .group_by(Subproject.project_id)
      .all()
)

# Single batched query for keyword totals
keyword_totals = dict(
    db.query(Subproject.project_id, func.sum(Subproject.keyword_count))
      .filter(Subproject.project_id.in_(project_ids))
      .group_by(Subproject.project_id)
      .all()
)

# Assign pre-calculated stats (FAST)
for project in projects:
    project.subproject_count = subproject_counts.get(project.id, 0)
    project.total_keywords = keyword_totals.get(project.id, 0)
```

**Performance Impact:**
- Before: N queries + Python loops = 3-10 seconds
- After: 3 queries total = < 1 second

---

### Rule #4: Lazy-Load Related Data

**❌ WRONG - Eager load everything:**
```python
# Loads 2,380 subprojects on every page load
projects = db.query(Project).options(
    joinedload(Project.subprojects)  # BAD: loads all related data
).all()

# Template renders all 2,380 rows (hidden by CSS)
return render_template("page.html", projects=projects)
```

**✅ CORRECT - Load on demand via HTMX:**
```python
# Initial page load: NO subprojects
@app.get("/projects")
def get_projects(page: int = 1):
    projects = db.query(Project).offset(...).limit(25).all()
    # Don't eager load subprojects
    return render_template("page.html", projects=projects)

# Separate endpoint for lazy-loading subprojects
@app.get("/projects/{project_id}/subprojects")
def get_subprojects(project_id: int):
    subprojects = db.query(Subproject).filter_by(project_id=project_id).all()
    return render_template("subprojects.html", subprojects=subprojects)
```

**HTMX Template Pattern:**
```html
<!-- Expand button triggers lazy-load -->
<button hx-get="/projects/{{ project.id }}/subprojects"
        hx-target="#subprojects-{{ project.id }}"
        hx-trigger="click once">
    Expand
</button>

<!-- Empty placeholder for HTMX to fill -->
<div id="subprojects-{{ project.id }}">
    <!-- Loaded on demand when user clicks expand -->
</div>
```

**Performance Impact:**
- Before: 3-10 seconds loading 2,380 subproject rows
- After: < 1 second loading 0 subprojects (load only when needed)

---

## 📏 CODE ORGANIZATION RULES

### File Size Limits (Mandatory)

**Line Count Guidelines:**
- 🟢 **Optimal:** 200-300 lines
- 🟡 **Acceptable:** 300-400 lines
- 🟠 **Warning:** 400+ lines (plan refactoring)
- 🔴 **Maximum:** 500 lines (split immediately)

**File Type Limits:**
- API Routes: 100-200 lines per file
- Service Classes: 150-300 lines
- Utility Functions: 100-200 lines
- Templates: 200-400 lines
- Test Files: Up to 800 lines (exception)

**When to Split a File:**
```python
# ❌ WRONG - Single 2,000-line file
# api/all_endpoints.py (2,000 lines)
@app.get("/projects")
def get_projects(): ...

@app.get("/subprojects")
def get_subprojects(): ...

@app.get("/keywords")
def get_keywords(): ...

# ... 50+ more endpoints
```

```python
# ✅ CORRECT - Split into focused files
# api/projects.py (150 lines)
@app.get("/projects")
def get_projects(): ...

# api/subprojects.py (120 lines)
@app.get("/subprojects")
def get_subprojects(): ...

# api/keywords.py (180 lines)
@app.get("/keywords")
def get_keywords(): ...
```

---

### Modular Architecture Pattern

**Directory Structure:**
```
src/
├── api/          # API endpoints (100-200 lines each)
│   ├── projects.py
│   ├── keywords.py
│   └── scraper.py
├── services/     # Business logic (150-300 lines each)
│   ├── project_service.py
│   ├── keyword_service.py
│   └── scraper_service.py
├── models/       # Database models (50-150 lines each)
│   ├── project.py
│   ├── keyword.py
│   └── scraping_job.py
├── workers/      # Background jobs (200-400 lines each)
│   └── scraper_worker.py
└── utils/        # Helper functions (100-200 lines each)
    ├── csv_parser.py
    └── file_utils.py
```

**Separation of Concerns:**
```python
# ✅ CORRECT - Each layer has one responsibility

# models/project.py - Just the data model
class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String(255))

# services/project_service.py - Business logic only
def create_project(db: Session, name: str) -> Project:
    project = Project(name=name)
    db.add(project)
    db.commit()
    return project

# api/projects.py - HTTP layer only
@app.post("/projects")
def create_project_endpoint(name: str, db: Session = Depends(get_db)):
    return ProjectService.create_project(db, name)
```

---

## 🔍 QUERY OPTIMIZATION PATTERNS

### Efficient Sorting with Subqueries

**❌ WRONG - Expensive GROUP BY over all joined data:**
```python
# Groups over 2,380 joined subproject rows
projects = db.query(Project).join(Subproject).group_by(Project.id)\
    .order_by(func.sum(Subproject.keyword_count).desc()).all()
```

**✅ CORRECT - Subquery calculates sum first:**
```python
# Step 1: Subquery calculates keyword totals per project
kw_subquery = db.query(
    Subproject.project_id.label("pid"),
    func.sum(Subproject.keyword_count).label("total_kw")
).group_by(Subproject.project_id).subquery()

# Step 2: Join subquery and order by pre-calculated total
projects = db.query(Project)\
    .outerjoin(kw_subquery, kw_subquery.c.pid == Project.id)\
    .order_by(kw_subquery.c.total_kw.desc())\
    .offset(offset).limit(page_size).all()
```

---

### Search Across Multiple Tables

**✅ CORRECT - Use subqueries with DISTINCT:**
```python
from sqlalchemy import distinct

# Subquery 1: Projects matching by name or SKU
base_query = db.query(Project).filter(
    or_(
        Project.name.ilike(f"%{search}%"),
        Project.sku.ilike(f"%{search}%")
    )
)

# Subquery 2: Projects with matching subprojects
subproject_matches = db.query(distinct(Subproject.project_id)).filter(
    or_(
        Subproject.name.ilike(f"%{search}%"),
        Subproject.first_keyword.ilike(f"%{search}%")
    )
).subquery()

# Subquery 3: Projects with matching keywords
keyword_matches = db.query(distinct(Keyword.subproject_id)).filter(
    Keyword.keyword.ilike(f"%{search}%")
).subquery()

subproject_ids_from_keywords = db.query(distinct(Subproject.project_id))\
    .filter(Subproject.id.in_(keyword_matches)).subquery()

# Combine all matches with OR
final_query = base_query.union(
    db.query(Project).filter(Project.id.in_(subproject_matches)),
    db.query(Project).filter(Project.id.in_(subproject_ids_from_keywords))
)
```

**Performance:** Comprehensive 5-field search completes in < 500ms for 2,380 subprojects.

---

## 🎨 UI/UX PATTERNS

### Always Show Loading States

**❌ WRONG - No feedback:**
```html
<div hx-get="/api/data">
    <!-- User sees nothing during load -->
</div>
```

**✅ CORRECT - Loading indicator:**
```html
<div hx-get="/api/data" hx-indicator="#spinner">
    <div id="spinner" class="htmx-indicator">
        Loading...
    </div>
</div>

<style>
.htmx-indicator { display: none; }
.htmx-request .htmx-indicator { display: inline; }
</style>
```

---

### Debounced Search Input

**❌ WRONG - API call on every keystroke:**
```html
<input type="text"
       hx-get="/api/search"
       hx-trigger="keyup">
```

**✅ CORRECT - 300ms debounce:**
```html
<input type="text"
       x-data="{ query: '' }"
       x-model="query"
       @input.debounce.300ms="htmx.ajax('GET', `/api/search?q=${query}`, {...})">
```

**Alpine.js Component:**
```javascript
Alpine.data('searchManager', () => ({
    searchQuery: '',

    searchItems() {
        // Auto-debounced by Alpine
        htmx.ajax('GET', `/api/items?q=${this.searchQuery}`, {
            target: '#results',
            swap: 'innerHTML'
        });
    }
}));
```

---

### Show Data Freshness

**✅ Always include last updated timestamp:**
```html
<div class="data-age">
    Last updated: {{ data.updated_at | timeago }}
</div>

<button hx-post="/api/refresh" hx-target="#data">
    🔄 Refresh Now
</button>
```

---

## 💾 CACHING PATTERNS

### Three-Table Strategy

**Architecture:**
```
1. raw_data         - Original API responses (7-day retention)
2. calculated_metrics - Pre-calculated metrics (updated every 30 min)
3. summary_dashboard  - Aggregated summaries (updated hourly)
```

**Usage:**
```python
# Background job (every 30 minutes)
@scheduler.scheduled_job('interval', minutes=30)
def calculate_metrics():
    # Process in batches
    for batch in get_batches(100):
        metrics = calculate_all_metrics(batch)
        db.bulk_insert_or_update(calculated_metrics, metrics)

# API endpoint (instant response)
@app.get("/metrics")
def get_metrics():
    # Just fetch pre-calculated data
    return db.query(CalculatedMetrics).limit(50).all()
```

---

### Event-Based Cache Invalidation

**Pattern:**
```python
def update_listing(asin: str, new_data: dict):
    # 1. Update database
    db.update_listing(asin, new_data)

    # 2. Invalidate related caches
    cache.delete(f"listing:{asin}")
    cache.delete(f"metrics:{asin}")
    cache.delete(f"dashboard:summary")

    # 3. Trigger background recalculation
    background_queue.enqueue(calculate_metrics, asin)
```

---

### Hybrid Real-Time/Cached Pattern

```python
def get_listing_display(asin: str):
    # Critical data - NEVER cache (price changes frequently)
    real_time = {
        "price": db.query_latest_price(asin),
        "inventory": db.query_current_inventory(asin)
    }

    # Metrics - OK to cache for 30 minutes
    cached_metrics = cache.get_or_calculate(
        f"metrics:{asin}",
        lambda: calculate_metrics(asin),
        ttl=1800  # 30 minutes
    )

    return {**real_time, **cached_metrics}
```

---

## 🔧 BACKGROUND JOB PATTERNS

### Thread-Based Worker (Recommended)

**✅ CORRECT - Simple, reliable pattern:**
```python
import threading
import time
from datetime import datetime

_worker_thread = None
_worker_stop = None

def _worker_loop(stop_event: threading.Event, interval: int = 30):
    logger.info(f"Worker started (interval: {interval}s)")

    # Run immediate tick on startup
    try:
        process_jobs()
    except Exception as e:
        logger.exception("Immediate tick failed")

    # Then run every N seconds
    while not stop_event.wait(interval):
        try:
            process_jobs()
        except Exception as e:
            logger.exception("Periodic tick failed")

def start_worker():
    global _worker_thread, _worker_stop

    if _worker_thread and _worker_thread.is_alive():
        logger.warning("Worker already running")
        return

    _worker_stop = threading.Event()
    _worker_thread = threading.Thread(
        target=_worker_loop,
        args=(_worker_stop,),
        name="background-worker",
        daemon=True
    )
    _worker_thread.start()

def stop_worker():
    if _worker_stop:
        _worker_stop.set()
    if _worker_thread:
        _worker_thread.join(timeout=5)
```

**Why This Over APScheduler:**
- Works with uvicorn --reload
- Simpler architecture
- Immediate tick on startup
- Guaranteed execution

---

### Job Statistics Synchronization

**Pattern to prevent counter drift:**
```python
def sync_job_statistics(db: Session, job: Job) -> None:
    """
    Sync job counters with actual database counts.
    Prevents counter drift after worker crashes/restarts.
    """
    # Count actual statuses from database (source of truth)
    completed = db.query(JobRow).filter(
        JobRow.job_id == job.id,
        JobRow.status == 'COMPLETED'
    ).count()

    failed = db.query(JobRow).filter(
        JobRow.job_id == job.id,
        JobRow.status == 'FAILED'
    ).count()

    # Check if out of sync
    if job.completed_rows != completed or job.failed_rows != failed:
        logger.warning(
            f"Job #{job.id} counters out of sync. "
            f"Completed: {job.completed_rows} → {completed}, "
            f"Failed: {job.failed_rows} → {failed}"
        )

        # Update counters from database
        job.completed_rows = completed
        job.failed_rows = failed

        # Auto-complete if all rows processed
        if completed + failed >= job.total_rows:
            job.status = 'COMPLETED'
            job.completed_at = datetime.utcnow()

        db.commit()

# Run on every worker tick
def process_jobs():
    for job in get_active_jobs():
        sync_job_statistics(db, job)  # Sync first
        process_job_rows(job)          # Then process
```

---

## 📋 SESSION MANAGEMENT

### Task Breakdown Rules

**Any task > 30 minutes needs subtasks:**
```markdown
## Current Task: Amazon Autocomplete
Started: 2025-10-03
Estimated Time: 3 hours

### Subtasks:
- [ ] Research Apify API docs (20 min)
- [ ] Design cache strategy (20 min)
- [ ] Create API endpoint (45 min)
- [ ] Implement business logic (60 min)
- [ ] Add caching layer (30 min)
- [ ] Write unit tests (30 min)
- [ ] Run Playwright tests (15 min)
```

---

### Documentation Update Rules

**CRITICAL: Update immediately after changes**

**When to update CLAUDE.md:**
- Adding new dependencies/packages
- Changing tech stack
- Major architecture decisions

**When to update database-schema.md:**
- Creating new tables
- Adding/modifying columns
- Changing relationships
- Adding indexes

**Pattern:**
```python
# After adding a package
# 1. Install package
pip install new-package

# 2. IMMEDIATELY update CLAUDE.md
"""
## Dependencies
- fastapi: Web framework
- sqlalchemy: ORM
- new-package: [WHY YOU ADDED IT]  # ← Add this line NOW
"""
```

---

### Context Management

**Use /clear between features:**
```
Feature A complete → /clear → Feature B start
```

**Use /compact at 70% capacity:**
```
Context: 140K / 200K tokens → /compact
```

**Update docs WHILE coding, not after:**
```
✅ Code change → Immediate doc update → Continue coding
❌ Code all features → Try to remember changes → Update docs
```

---

## ✅ TESTING REQUIREMENTS

### End-to-End Testing Checklist

**For EVERY new feature, test:**
- [ ] Page loads without errors
- [ ] Data displays correctly
- [ ] Pagination works (if applicable)
- [ ] Search/filter works (if applicable)
- [ ] Manual refresh updates data
- [ ] Loading indicators show/hide properly
- [ ] Error states display correctly
- [ ] No console errors
- [ ] Performance: Page loads < 3 seconds
- [ ] Works with empty datasets
- [ ] Works with large datasets (1000+ items)

---

### Performance Benchmarks

**Target Metrics:**
- Initial page load: < 1 second
- Paginated list (50 items): < 2 seconds
- Search results: < 3 seconds
- HTMX partial update: < 500ms
- Background calculation: Async, no user impact

**If these targets aren't met:**
1. Add pagination (if missing)
2. Move calculations to background
3. Implement lazy-loading
4. Add database indexes
5. Use batched aggregation

---

## 🎯 QUICK REFERENCE CHECKLIST

### Before Writing Code:
- [ ] File will be under 400 lines (or split it)
- [ ] Pagination implemented (max 50-100 items)
- [ ] No calculations on page load
- [ ] Loading states for all async operations
- [ ] Database queries are optimized (no N+1)

### After Writing Code:
- [ ] File is actually under 400 lines
- [ ] Tests pass (especially performance)
- [ ] Documentation updated (if schemas/deps changed)
- [ ] No console errors in browser
- [ ] Page loads in < 3 seconds

### Before Committing:
- [ ] All files under 500 lines
- [ ] Tests written and passing
- [ ] Documentation reflects changes
- [ ] Performance benchmarks met
- [ ] No debug code left in

---

## 🏆 SUCCESS METRICS

**You're doing it right if:**
- Page loads are consistently < 1 second
- Users can browse 100K+ records smoothly
- Code files stay under 400 lines
- No "this is slow" user complaints
- Background jobs handle heavy calculations
- Database queries are < 100ms (most < 50ms)

**Warning signs:**
- Page loads > 3 seconds
- Files approaching 500+ lines
- Calculations happening on page load
- No pagination on large datasets
- N+1 query problems in logs
- Users complaining about slowness

---

## 📚 RESOURCES FROM THIS PROJECT

**Key Documents to Reference:**
- `docs/development-log.md` - Technical decisions and solutions
- `docs/patterns.md` - Proven development patterns
- `docs/coding-standards.md` - File size limits and conventions
- `CLAUDE.md` - Context management approach

**Performance Optimizations Applied:**
- Phase 7 Test 12: Pipeline pagination (3-10s → <1s)
- Phase 7 Test 11: Thread-based worker (reliable ticks)
- Phase 7 Test 10: Job statistics sync (prevents drift)
- Phase 6: Event delegation (67% token reduction)

---

## 🎓 FINAL ADVICE

**The #1 Rule:**
> If you're loading more than 100 items at once, you're probably doing it wrong.

**The #2 Rule:**
> If calculations take > 1 second, do them in the background.

**The #3 Rule:**
> Keep files under 400 lines or Claude Code will struggle.

**Remember:**
- Performance comes from architecture, not optimization tricks
- Small, focused files are easier to maintain
- Pre-calculation beats real-time calculation
- Pagination is mandatory, not optional
- Database aggregation beats Python loops
- Lazy-loading beats eager-loading
- Background jobs beat page-load calculations

---

**Last Updated:** 2025-10-18
**Based on:** Listings Workflow project (Phases 1-9)
**Project Scale:** 2M+ records, 2,380 subprojects, 10K+ keywords per subproject
