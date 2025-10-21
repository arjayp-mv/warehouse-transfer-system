# Warehouse Transfer Planning Tool - AI Assistant Guidelines

## Project Overview
This project is building a web-based tool to optimize inventory transfers from Burnaby (Canada) warehouse to Kentucky (US) warehouse. The system replaces a complex Excel-based process with an intelligent solution that accounts for stockouts and provides data-driven transfer recommendations.

## Key Business Context

### Current Pain Points
1. **Stockout Blindness**: Monthly sales data doesn't reflect true demand when items are out of stock
2. **No Historical Visibility**: Can't see CA vs US sales breakdown without re-pulling reports
3. **Manual Process**: Time-consuming calculations for 2000+ SKUs (growing to 3-4K)
4. **Human Error**: Manual Excel formulas prone to mistakes
5. **Reactive Management**: No systematic approach to safety stock levels

### Business Rules
- **Transfer Frequency**: Monthly (bi-weekly during busy season)
- **Transit Time**: 1 week shipping + 2 weeks preparation = 3 weeks total
- **Minimum Transfer**: 10 units per SKU
- **Transfer Multiples**: 
  - Chargers/cables: 25 units
  - Standard items: 50 units  
  - High-volume items: 100 units
- **Coverage Target**: ~6 months (varies by ABC-XYZ classification)
- **Stockout Correction**: Minimum 30% availability factor to avoid overcorrection

## Technical Architecture

### Stack Decision Rationale
- **Backend**: Python/FastAPI (chosen for calculation speed, no build process)
- **Database**: MySQL via XAMPP (simple, familiar, sufficient for scale)
- **Frontend**: Plain HTML/JS with DataTables (no build complexity, powerful features)

## Important
DO NOT CODE WITH EMOJIS!

### Core Algorithms

#### Stockout-Corrected Demand (Monthly Data Only)
```python
# Simple approach using monthly sales + stockout days count
def correct_monthly_demand(monthly_sales, stockout_days_in_month):
    days_in_month = 30  # or actual days in month
    availability_rate = (days_in_month - stockout_days_in_month) / days_in_month
    
    if availability_rate < 1.0 and monthly_sales > 0:
        correction_factor = max(availability_rate, 0.3)  # 30% floor prevents overcorrection
        corrected_demand = monthly_sales / correction_factor
        
        # Cap at 50% increase for very low availability
        if availability_rate < 0.3:
            corrected_demand = min(corrected_demand, monthly_sales * 1.5)
    else:
        corrected_demand = monthly_sales
    
    return corrected_demand
```

#### Transfer Calculation
```python
target_inventory = corrected_monthly_demand * coverage_months
current_position = kentucky_qty + pending_qty
transfer_need = target_inventory - current_position
# Round to multiple and check Burnaby availability
final_qty = round_to_multiple(min(transfer_need, burnaby_available))
```

## Data Sources & Update Frequency

### Current Data Flow
1. **Monthly**: Full sales report with warehouse breakdown
2. **As Needed**: Current inventory snapshots before transfers
3. **Manual**: Stockout tracking (needs automation)

### Recommended Update Cadence
- **Monthly**: Sales data + stockout days count
- **Before Transfers**: Current inventory snapshot  
- **As Needed**: Manual stockout day adjustments

## Important Implementation Notes

### Priority Features (Must Have)
1. Stockout detection and demand correction
2. Historical sales visibility (CA vs US breakdown)
3. Transfer quantity recommendations with rounding
4. Excel import/export functionality
5. Visual urgency indicators (color coding)

### Known Challenges
1. **Stockout Detection**: Need to manually track or estimate stockout days per month
2. **Master Carton Data**: Not available but desired for rounding
3. **Lead Time Variability**: Suppliers have different lead times (not tracked)
4. **Historical Data**: May need to backfill stockout days for recent months

### User Workflow
1. Upload monthly sales data with stockout days count
2. Upload current inventory snapshot
3. System applies stockout correction to demand
4. Review transfer recommendations (sorted by urgency)
5. Adjust quantities as needed
6. Export transfer order for execution

## Key Metrics to Track

### Operational
- Stockout days per SKU
- Coverage days (current and after transfer)
- Transfer accuracy (recommended vs actual)

### Strategic  
- Inventory turnover improvement
- Service level by ABC class
- Cash flow impact

## Testing Requirements

### Always Use Playwright MCP
When testing the web interface, **always use the Playwright MCP tools** for:
- **UI Testing**: Verify forms, buttons, and data tables work correctly
- **Data Flow**: Test import/export functionality with real files
- **Visual Validation**: Confirm color coding, badges, and alerts display properly
- **Performance**: Test with full dataset (4000+ SKUs) for responsiveness
- **User Workflows**: End-to-end testing of complete transfer planning process

### Playwright Testing Checklist
- [ ] Dashboard loads and displays correct metrics
- [ ] Transfer planning table sorts and filters properly
- [ ] Excel import handles various file formats gracefully
- [ ] Export generates valid Excel files with correct data
- [ ] Stockout correction calculations are mathematically accurate
- [ ] Transfer quantities round to proper multiples
- [ ] Performance remains acceptable with large datasets
- [ ] Error handling works for invalid inputs
- [ ] Visual indicators (red/yellow/green) display correctly

### Test Scenarios
1. **Currently Out of Stock**: SKU with 0 inventory, verify urgent priority
2. **Recent Stockout Recovery**: SKU back in stock, verify correction applied
3. **New SKU**: No historical data, verify graceful handling
4. **Seasonal SKU**: Irregular demand, verify XYZ classification
5. **Death Row SKU**: Pending discontinuation, verify appropriate coverage
6. **Large Dataset**: 4000+ SKUs, verify performance under load

### Performance Targets
- Handle 4000 SKUs without lag
- Generate recommendations in <5 seconds
- Export Excel in <10 seconds
- Page load times <2 seconds

## Common Queries You May Receive

1. "How do we handle items that have been out for months?"
   - Use historical demand from before stockout
   - Apply urgency multiplier (1.5x for >7 days out)

2. "What about seasonal products?"
   - XYZ classification handles variability
   - Consider separate seasonal coverage targets

3. "How accurate is the stockout correction?"
   - 30% floor prevents overcorrection
   - Validate with actual restocking results

## File Structure
```
warehouse-transfer/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── calculations.py      # Core business logic
│   ├── database.py         # Database connections
│   └── models.py           # Data models
├── frontend/
│   ├── index.html          # Dashboard
│   ├── transfer-planning.html # Main interface
│   ├── sku-listing.html    # SKU inventory management
│   └── js/app.js          # Frontend logic
├── database/
│   └── schema.sql         # Database structure
└── docs/
    ├── CLAUDE.md          # This file
    ├── PRD-v2.md         # Detailed requirements
    └── TASKS.md          # Implementation roadmap
```

## Frontend Access URLs
- **Development Server**: `http://localhost:8000` (FastAPI with static file serving, caching disabled)
- **Production Server**: `http://localhost:8000` (FastAPI with static file serving, caching enabled)
- **SKU Listing**: `http://localhost:8000/static/sku-listing.html`
- **Dashboard**: `http://localhost:8000/static/index.html`
- **Transfer Planning**: `http://localhost:8000/static/transfer-planning.html`

## Development Philosophy

### Keep It Simple
- No unnecessary complexity
- Proven methods over cutting-edge
- User experience over features

### Iterate Quickly
- Start with MVP (min-max model)
- Add complexity only when validated
- Measure impact of each addition

### Focus on Value
- Every feature must reduce time or improve accuracy
- Prioritize based on business impact
- Document ROI for stakeholders

## Task Management Protocol

### TASKS.md Archive Structure (Updated 2025-10-18)

The project now uses an archive-based task tracking system to maintain manageable file sizes while preserving complete historical details.

**Current Structure**:
- **TASKS.md** (main file): High-level summaries and current status (under 400 lines)
- **TASKS_ARCHIVE_V1-V4.md**: Foundation and Transfer Planning (Tasks 001-100)
- **TASKS_ARCHIVE_V5.md**: Supplier Analytics System (Tasks 101-175)
- **TASKS_ARCHIVE_V6.md**: Sales and SKU Analytics (Tasks 176-377)

### Managing Future Tasks

#### When Starting a New Major Version (V7.0+)

If you need to add a new major feature or version:

1. **Add to Main TASKS.md**:
   - Create a new version section with high-level summary (3-4 paragraphs)
   - List key features to be delivered
   - Include task range (e.g., Tasks 378-450)
   - Add link placeholder to future archive file

2. **Work on Tasks**:
   - Track detailed tasks in main TASKS.md during active development
   - Use standard task format with clear descriptions
   - Mark tasks as completed immediately after finishing

3. **When Version Completes** (or main TASKS.md exceeds 400 lines):
   - Create new archive file: `TASKS_ARCHIVE_V7.md`
   - Move detailed task lists to archive with full context
   - Replace detail in main TASKS.md with summary and archive link
   - Update "Archive Navigation" section in main TASKS.md

#### Example: Adding V7.0 Advanced Forecasting

**Step 1**: Add to main TASKS.md
```markdown
## V7.0: Advanced Demand Forecasting System (IN PROGRESS)

Summary: Machine learning-based demand forecasting using historical
sales patterns, seasonal trends, and external factors.

Key Features to Deliver:
- Time series analysis with ARIMA/Prophet models
- Seasonal decomposition and trend detection
- Forecast confidence intervals
- Integration with transfer planning

Task Range: TASK-378 to TASK-425

Detailed Documentation: [TASKS_ARCHIVE_V7.md](TASKS_ARCHIVE_V7.md)
(when completed)
```

**Step 2**: Track tasks during development
```markdown
### Phase 1: Data Preparation
- [ ] TASK-378: Create forecasting database schema
- [ ] TASK-379: Implement data aggregation pipeline
- [x] TASK-380: Add seasonal decomposition functions
```

**Step 3**: When complete, create archive and update main file

### Task Naming Conventions

**Continue Sequential Numbering**:
- Last completed task: TASK-377
- Next new task: TASK-378
- Format: `TASK-XXX: Brief description`

**Version Naming**:
- Major new feature: V7.0, V8.0, etc.
- Bug fixes/enhancements: V7.1, V7.2, etc.
- Critical fixes: V7.1.1, V7.1.2, etc.

### File Size Management Rules

**Main TASKS.md**:
- Target: 300-400 lines
- Maximum: 500 lines
- When exceeding 400 lines: Archive oldest completed version

**Archive Files**:
- No strict limit (typically 350-650 lines)
- One archive per major version or logical grouping
- Include complete task details, code examples, technical notes

### Task Status Format
Use clear status indicators in TASKS.md:
```markdown
- [x] **TASK-001**: Completed task (standard GitHub format)
- [ ] **TASK-002**: Pending task (not started)
- [~] **TASK-003**: In progress task (currently working on)
- [!] **TASK-004**: Blocked task (needs resolution before proceeding)
- [?] **TASK-005**: Needs clarification from stakeholder
```

### Archive File Template

When creating a new archive file, use this structure:

```markdown
# Warehouse Transfer Planning Tool - VX.X Archive

Task Range: TASK-XXX to TASK-XXX
Status: ALL COMPLETED
Archive Date: YYYY-MM-DD

---

## VX.0: Feature Name

Feature Overview:
[2-3 paragraph description]

### Phase 1: [Phase Name]
Completed Tasks:
- [x] TASK-XXX: Description with technical details
- [x] TASK-XXX: Description

Implementation Details:
[Code examples, algorithms, key decisions]

### Phase 2: [Phase Name]
[Continue pattern...]

---

## Summary of VX.X Achievements

Key Features Delivered:
- Feature 1 with business impact
- Feature 2 with technical achievement

Business Impact:
[Quantifiable results]

Technical Achievements:
[Performance, code quality, etc.]

---

Previous Features: [Link to earlier archive]
Next Evolution: [Link to next archive]
Return to Main Tracker: [TASKS.md](TASKS.md)
```

### When Tasks Change During Development
- **Scope Increase**: Add new tasks with clear dependencies
- **Complexity Changes**: Break large tasks into smaller subtasks
- **Timeline Impact**: Update version milestones if needed
- **Dependencies**: Note which tasks block others
- **Archive Timing**: Move to archive when version completes OR file size exceeds limits

### Maintenance Checklist

Before committing changes:
- [ ] Main TASKS.md is under 400 lines
- [ ] All completed tasks marked with [x]
- [ ] Version summaries are accurate and concise
- [ ] Archive links are correct and functional
- [ ] New tasks follow sequential numbering
- [ ] No emojis in task descriptions (project standard)
- [ ] Business impact clearly stated for each version

This archive structure ensures TASKS.md remains maintainable while preserving complete project history.

## Code Documentation Standards

### Documentation Requirements (Critical!)

All code MUST be properly documented following these standards:

#### Python Files (.py)
```python
"""
Module-level docstring explaining the file's purpose
Describe what this module does and its main responsibilities
"""

class ExampleClass:
    """
    Class-level docstring explaining the class purpose
    
    Attributes:
        attribute_name: Description of the attribute
        
    Example:
        Basic usage example:
        
        instance = ExampleClass()
        result = instance.method()
    """
    
    def method_name(self, param1: str, param2: int = 0) -> bool:
        """
        Method docstring with clear description
        
        Args:
            param1: Description of parameter 1
            param2: Description of parameter 2 (default: 0)
            
        Returns:
            Description of return value
            
        Raises:
            ValueError: When parameter validation fails
            ConnectionError: When database connection fails
        """
        # Inline comments for complex logic
        if param1 == "special_case":
            # Explain why this special case exists
            return self._handle_special_case()
        
        return True
```

#### HTML Files (.html)
```html
<!DOCTYPE html>
<!-- 
Warehouse Transfer Planning Tool - Dashboard
Main dashboard interface showing key metrics and navigation
Features: Real-time metrics, alerts, responsive design
-->
<html lang="en">
<head>
    <!-- Meta tags and dependencies -->
    <meta charset="UTF-8">
    <title>Dashboard - Warehouse Transfer Tool</title>
</head>
<body>
    <!-- Main navigation -->
    <nav class="navbar">
        <!-- Navigation content -->
    </nav>
    
    <!-- Dashboard content -->
    <main>
        <!-- Key metrics section -->
        <section class="metrics-section">
            <!-- Metric cards displaying real-time data -->
        </section>
    </main>
</body>
</html>
```

#### JavaScript Code
```javascript
/**
 * Dashboard data management functions
 * Handles API calls, data updates, and UI interactions
 */

/**
 * Load dashboard metrics from the backend API
 * Updates all metric cards and handles error states
 * @returns {Promise<void>}
 */
async function loadDashboardData() {
    try {
        showLoading(true);
        
        // Fetch data from API with error handling
        const response = await fetch('/api/dashboard');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        // Process and display data
        const data = await response.json();
        updateMetrics(data.metrics);
        
    } catch (error) {
        console.error('Failed to load dashboard:', error);
        showError('Unable to load dashboard data');
    } finally {
        showLoading(false);
    }
}
```

### Current Documentation Status

#### ✅ Well-Documented Files:
- **calculations.py**: Excellent docstrings with Args/Returns
- **database.py**: Good function documentation
- **main.py**: Clear module description and purpose
- **models.py**: Basic class documentation

#### 🔄 Needs Enhancement:
- **Frontend HTML**: Add more detailed component comments
- **JavaScript**: Add JSDoc-style function documentation
- **API Endpoints**: Need detailed OpenAPI/Swagger docs

### Documentation Checklist

Before marking any task as complete, verify:

- [ ] **Module Docstring**: Every .py file has a clear module description
- [ ] **Function Docstrings**: All functions have Args/Returns/Raises
- [ ] **Class Docstrings**: Classes explain purpose and usage examples
- [ ] **Inline Comments**: Complex business logic is explained
- [ ] **HTML Comments**: Sections and components are labeled
- [ ] **JavaScript Docs**: Functions use JSDoc format
- [ ] **API Documentation**: FastAPI auto-generates docs from docstrings
- [ ] **README Updates**: Any new features documented in project README

### Business Logic Documentation Priority

Pay special attention to documenting:

1. **Stockout Correction Algorithm**: Mathematical formulas and edge cases
2. **ABC-XYZ Classification**: Classification criteria and thresholds  
3. **Transfer Calculations**: Rounding logic and validation rules
4. **Priority Scoring**: How urgency levels are determined
5. **Data Import/Export**: File format requirements and validation
6. **API Endpoints**: Request/response schemas and error codes

### Code Comments Best Practices

```python
# ❌ Bad: Obvious comment
total = price * quantity  # Calculate total

# ✅ Good: Explains business logic
# Apply 30% floor to prevent overcorrection during severe stockouts
correction_factor = max(availability_rate, 0.3)

# ✅ Good: Explains why, not what
# Use historical demand from before stockout period started
# because current month shows zero sales due to unavailability
if current_month_sales == 0 and stockout_days > 0:
    demand = get_historical_average(sku_id, months_back=3)
```

### Documentation Maintenance

- **After Each Function**: Add/update docstring before moving on
- **Complex Algorithms**: Add mathematical explanations and examples
- **API Changes**: Update endpoint documentation immediately
- **Frontend Updates**: Document new UI components and interactions
- **Database Changes**: Update schema comments and model docs

This ensures the codebase remains maintainable and understandable for future developers and stakeholders.

## When to Escalate

Contact the user if:
1. Fundamental business rules seem incorrect
2. Data quality issues block progress
3. Scope creep beyond initial requirements
4. Performance issues with full dataset
5. Tasks are consistently taking longer than estimated
6. Documentation requirements are unclear or conflicting

## Resources & References

### Knowledge Base
- `claudeconvo.md` - Initial requirements discussion
- `PRD.md` - Original PRD (being updated)
- `stockout.md` - Stockout handling refinements
- `inventory.md` - Update frequency guidelines
- `forecasting-transcript.md` - Forecasting methodology
- `inventory-management.md` - Inventory optimization principles

### Key Formulas
- **Safety Stock**: Z-score × demand_std × sqrt(lead_time)
- **Reorder Point**: average_demand × lead_time + safety_stock
- **Economic Order Quantity**: sqrt(2 × demand × order_cost / holding_cost)
- **ABC Classification**: 80/15/5 value distribution
- **XYZ Classification**: CV < 0.25 (X), < 0.50 (Y), >= 0.50 (Z)

## Success Criteria

The tool is successful when:
1. Transfer planning time drops from hours to <30 minutes
2. Stockout incidents reduce by 50%
3. Inventory turnover improves by 20%
4. Users prefer it over Excel (adoption rate >90%)

## Remember

This tool directly impacts company cash flow and customer satisfaction. Every SKU out of stock is lost revenue. Every excess unit is trapped cash. The balance is delicate but achievable with the right data and logic.

When in doubt, refer to the PRD-v2.md for detailed requirements and TASKS.md for implementation priorities.

## Development & Deployment Management

### Development Environment Setup

#### Server Management Scripts
- **`run_dev.bat`**: Starts development server with hot reload and caching disabled
- **`kill_server.bat`**: Comprehensive process cleanup for stuck/phantom processes
- **`run_production.bat`**: Starts production server with caching enabled

#### Environment Configuration
- **`.env`**: Development configuration (DEBUG=true, caching disabled)
- **`.env.production`**: Production template (DEBUG=false, caching enabled)

#### Development Workflow
1. **Starting Development**: Use `run_dev.bat` (never start uvicorn manually)
2. **Server Issues**: Use `kill_server.bat` if server gets stuck on port 8000
3. **Testing Changes**: Development mode disables static file caching automatically
4. **Port Management**: Scripts handle process cleanup to avoid port conflicts

#### Common Development Issues & Solutions

**Problem**: Code changes not showing up in browser
**Solution**: Development mode automatically disables static file caching when `DEBUG=true`

**Problem**: Server won't start due to "port already in use"
**Solution**: Run `kill_server.bat` to clean up phantom processes

**Problem**: Need to switch ports constantly
**Solution**: Use the provided scripts - they handle process management automatically

### Production Deployment

#### Pre-Deployment Checklist
- [ ] Copy `.env.production` to `.env`
- [ ] Verify `DEBUG=false` in environment
- [ ] Remove development-only dependencies
- [ ] Test with production settings using `run_production.bat`

#### Files to Exclude from Git/Production
```gitignore
# Development environment
.env                    # Contains DEBUG=true
__pycache__/           # Python cache
*.pyc                  # Compiled Python
.pytest_cache/         # Test cache

# Development scripts (optional)
run_dev.bat            # Development-only
kill_server.bat        # Development-only
```

#### Production Environment Variables
```bash
# Required for production
DEBUG=false
ENVIRONMENT=production
FASTAPI_RELOAD=false
LOG_LEVEL=warning
```

#### Code Changes for Production

**backend/main.py**:
- Static file caching is automatically enabled when `DEBUG=false`
- No code changes needed - environment variables control behavior

**Security Considerations**:
- Change CORS origins from "*" to specific domains in production
- Use proper database credentials (not development defaults)
- Enable HTTPS in production deployment

### Environment-Specific Behavior

#### Development Mode (`DEBUG=true`)
- Static file caching disabled via monkey patching
- Hot reload enabled for all file types
- Detailed logging enabled
- CORS allows all origins

#### Production Mode (`DEBUG=false`)
- Static file caching enabled for performance
- No hot reload
- Warning-level logging only
- Restricted CORS origins (update in main.py)

### Troubleshooting

#### Phantom Process Issues (Windows)
If `kill_server.bat` shows "Port still in use" warnings:
1. Restart Windows to clear phantom TCP connections
2. Check Windows Firewall isn't blocking process termination
3. Use Task Manager to verify no python.exe processes remain

#### Environment Detection Issues
If caching behavior isn't working correctly:
1. Verify `.env` file is in project root
2. Check `python-dotenv` is installed
3. Restart server after changing environment variables

#### Performance Issues
If development server is slow:
1. Switch to production mode temporarily: `run_production.bat`
2. Check if too many file watchers are active
3. Reduce `--reload-include` patterns if needed

This comprehensive setup eliminates the cache and server restart issues that were causing development friction.