import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, timedelta, datetime
from fpdf import FPDF
import io
import calendar

# -------------------------------------------------------------------
# 1. Configuration & Constants — CAO Glastuinbouw
# -------------------------------------------------------------------
DAILY_LIMIT_HOURS = 12.0
WEEKLY_HARD_LIMIT_HOURS = 60.0
WEEKLY_AVG_LIMIT_HOURS = 48.0
ROLLING_PERIOD_WEEKS = 16
MIN_REST_BETWEEN_SHIFTS_HOURS = 11.0
MAX_CONSECUTIVE_WORK_DAYS = 6

# Payment cap rate: monthly max = this rate × business days in month
# e.g. 9.6h × 21 days = 201.6h max paid; surplus → urenbank
DAILY_PAID_CAP_HOURS = 9.6

# Dutch public holidays (2025-2026 dates)
DUTCH_HOLIDAYS_2025 = [
    date(2025, 1, 1),    # Nieuwjaarsdag
    date(2025, 4, 18),   # Goede Vrijdag
    date(2025, 4, 20),   # Eerste Paasdag
    date(2025, 4, 21),   # Tweede Paasdag
    date(2025, 4, 27),   # Koningsdag
    date(2025, 5, 5),    # Bevrijdingsdag
    date(2025, 5, 29),   # Hemelvaartsdag
    date(2025, 6, 8),    # Eerste Pinksterdag
    date(2025, 6, 9),    # Tweede Pinksterdag
    date(2025, 12, 25),  # Eerste Kerstdag
    date(2025, 12, 26),  # Tweede Kerstdag
]

DUTCH_HOLIDAYS_2026 = [
    date(2026, 1, 1),    # Nieuwjaarsdag
    date(2026, 4, 3),    # Goede Vrijdag
    date(2026, 4, 5),    # Eerste Paasdag
    date(2026, 4, 6),    # Tweede Paasdag
    date(2026, 4, 27),   # Koningsdag
    date(2026, 5, 5),    # Bevrijdingsdag
    date(2026, 5, 14),   # Hemelvaartsdag
    date(2026, 5, 24),   # Eerste Pinksterdag
    date(2026, 5, 25),   # Tweede Pinksterdag
    date(2026, 12, 25),  # Eerste Kerstdag
    date(2026, 12, 26),  # Tweede Kerstdag
]

ALL_HOLIDAYS = set(DUTCH_HOLIDAYS_2025 + DUTCH_HOLIDAYS_2026)

# Strawberry greenhouse seasons
STRAWBERRY_SEASONS = {
    'Sadzenie / Przygotowanie': {'months': [9, 10, 11], 'intensity': 'medium', 'color': '#D4A574'},
    'Pielęgnacja zimowa': {'months': [12, 1, 2], 'intensity': 'low', 'color': '#7FB5D5'},
    'Wzrost / Kwitnienie': {'months': [3, 4], 'intensity': 'medium', 'color': '#90C695'},
    'Zbiory (piek!)': {'months': [5, 6, 7], 'intensity': 'high', 'color': '#E8686A'},
    'Po zbiorach / Czyszczenie': {'months': [8], 'intensity': 'medium', 'color': '#C4A6D6'},
}

# Wettelijk verlof: 4x weekly hours (e.g. 40h/wk = 160h = 20 days)
LEGAL_LEAVE_MULTIPLIER = 4  # weeks of leave per year

# Contract types
CONTRACT_TYPES = {
    'vast': 'Stały (vast contract)',
    'bepaald': 'Czasowy (bepaalde tijd)',
    'nul_uren': 'Kontrakt 0-godzin (nul-urencontract)',
    'min_max': 'Min-Max kontrakt',
}

st.set_page_config(
    page_title="🍓 Szklarnia HR — Śledzenie Czasu Pracy",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -------------------------------------------------------------------
# Custom CSS
# -------------------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&display=swap');
    
    .block-container { padding-top: 1.5rem; }
    
    h1, h2, h3 { font-family: 'DM Sans', sans-serif !important; }
    
    .season-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85em;
        font-weight: 600;
        color: #fff;
        margin: 2px;
    }
    .alert-card {
        border-left: 4px solid;
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        margin: 8px 0;
    }
    .alert-red { border-color: #e53e3e; background-color: #fff5f5; }
    .alert-orange { border-color: #dd6b20; background-color: #fffaf0; }
    .alert-green { border-color: #38a169; background-color: #f0fff4; }
    .alert-blue { border-color: #3182ce; background-color: #ebf8ff; }
    
    .metric-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 12px;
        color: white;
        text-align: center;
    }
    
    .kpi-row {
        display: flex; gap: 12px; margin: 12px 0;
    }
    .kpi-box {
        flex: 1;
        background: #f7fafc;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        border: 1px solid #e2e8f0;
    }
    .kpi-box .value {
        font-size: 1.8em;
        font-weight: 700;
        color: #2d3748;
    }
    .kpi-box .label {
        font-size: 0.85em;
        color: #718096;
        margin-top: 4px;
    }
</style>
""", unsafe_allow_html=True)


# -------------------------------------------------------------------
# 2. Data Loading & Processing
# -------------------------------------------------------------------
@st.cache_data
def load_dummy_data():
    """Generates realistic dummy data for a strawberry greenhouse."""
    np.random.seed(42)
    
    employees = {
        'Jan de Vries': {'contract': 'vast', 'hours': 40.0, 'start_date': '2020-03-01'},
        'Anna Kowalska': {'contract': 'nul_uren', 'hours': 0.0, 'start_date': '2024-04-01'},
        'Piotr Nowak': {'contract': 'nul_uren', 'hours': 0.0, 'start_date': '2024-04-15'},
        'Maria Ionescu': {'contract': 'bepaald', 'hours': 32.0, 'start_date': '2024-01-15'},
        'Sofia Petrova': {'contract': 'nul_uren', 'hours': 0.0, 'start_date': '2024-05-01'},
        'Krzysztof Wójcik': {'contract': 'min_max', 'hours': 24.0, 'start_date': '2023-06-01'},
        'Elena Dimitrova': {'contract': 'nul_uren', 'hours': 0.0, 'start_date': '2024-05-01'},
        'Tomasz Zieliński': {'contract': 'vast', 'hours': 38.0, 'start_date': '2021-09-01'},
    }
    
    start_date = date.today() - timedelta(weeks=24)
    dates = [start_date + timedelta(days=i) for i in range(168)]
    
    data = []
    for emp, info in employees.items():
        emp_start = datetime.strptime(info['start_date'], '%Y-%m-%d').date()
        for d in dates:
            if d < emp_start:
                continue
            month = d.month
            
            # Determine season intensity
            if month in [5, 6, 7]:  # Harvest — high intensity
                base_hours = np.random.uniform(8, 13)
                skip_prob = 0.05
            elif month in [3, 4, 9, 10, 11]:  # Medium
                base_hours = np.random.uniform(6, 10)
                skip_prob = 0.15
            else:  # Low
                base_hours = np.random.uniform(4, 8)
                skip_prob = 0.35
            
            # Sundays: less likely to work
            if d.weekday() == 6:
                skip_prob = 0.85
                base_hours = np.random.uniform(4, 7)
            elif d.weekday() == 5:
                skip_prob = 0.3
                base_hours = np.random.uniform(5, 10)
                
            # 0-hour contracts: more irregular
            if info['contract'] == 'nul_uren':
                skip_prob += 0.15
                
            if np.random.rand() < skip_prob:
                continue
                
            hours = round(base_hours, 1)
            
            # Simulate start/end times
            start_hour = np.random.choice([6, 7, 8])
            end_decimal = start_hour + hours
            end_hour = int(end_decimal)
            end_min = int((end_decimal - end_hour) * 60)
            
            data.append({
                'Employee': emp,
                'Date': d,
                'Hours_Worked': hours,
                'Start_Time': f"{start_hour:02d}:00",
                'End_Time': f"{end_hour:02d}:{end_min:02d}",
            })
    
    df = pd.DataFrame(data)
    df['Date'] = pd.to_datetime(df['Date'])
    df['Week_Number'] = df['Date'].dt.isocalendar().week.astype(int)
    df['Year'] = df['Date'].dt.isocalendar().year.astype(int)
    return df, employees


def process_uploaded_file(uploaded_file):
    """Processes CSV or Excel from Duinkier."""
    try:
        if uploaded_file.name.endswith('.csv'):
            try:
                df = pd.read_csv(uploaded_file, encoding='utf-8', sep=';', decimal=',',
                                 header=None, names=['Date', 'Employee_ID', 'Employee', 'Hours_Worked'])
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding='iso-8859-1', sep=';', decimal=',',
                                 header=None, names=['Date', 'Employee_ID', 'Employee', 'Hours_Worked'])
        elif uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file, header=None,
                               names=['Date', 'Employee_ID', 'Employee', 'Hours_Worked'])
        else:
            st.error("Nieobsługiwany format. Prześlij CSV lub Excel.")
            return None, None

        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        df['Hours_Worked'] = pd.to_numeric(df['Hours_Worked'], errors='coerce')
        df = df.dropna(subset=['Date', 'Hours_Worked'])
        df['Week_Number'] = df['Date'].dt.isocalendar().week.astype(int)
        df['Year'] = df['Date'].dt.isocalendar().year.astype(int)
        
        # Build basic employee dict from data
        employees = {}
        for emp in df['Employee'].unique():
            employees[emp] = {'contract': 'nul_uren', 'hours': 0.0, 'start_date': str(df[df['Employee']==emp]['Date'].min().date())}
        
        return df, employees
    except Exception as e:
        st.error(f"Błąd przetwarzania pliku: {e}")
        return None, None


# -------------------------------------------------------------------
# 3. Leave & Absence Tracking (Session State)
# -------------------------------------------------------------------
def init_leave_data():
    """Initialize leave/absence tracking in session state."""
    if 'leave_records' not in st.session_state:
        st.session_state.leave_records = []
    if 'sick_records' not in st.session_state:
        st.session_state.sick_records = []

def add_leave_record(employee, start, end, leave_type, notes=""):
    """Add a leave record."""
    st.session_state.leave_records.append({
        'Employee': employee,
        'Start_Date': start,
        'End_Date': end,
        'Type': leave_type,
        'Days': np.busday_count(
            np.datetime64(start), 
            np.datetime64(end) + np.timedelta64(1, 'D')
        ),
        'Notes': notes,
        'Status': 'Zatwierdzony',
    })

def add_sick_record(employee, start, end=None, recovered=False, notes=""):
    """Add a sick leave record."""
    st.session_state.sick_records.append({
        'Employee': employee,
        'Start_Date': start,
        'End_Date': end if end else None,
        'Recovered': recovered,
        'Notes': notes,
    })


# -------------------------------------------------------------------
# 4. CAO Compliance Engine
# -------------------------------------------------------------------
def check_full_compliance(df):
    """Comprehensive CAO Glastuinbouw compliance checks."""
    violations = []
    
    if df.empty:
        return violations, pd.DataFrame()
    
    for emp in df['Employee'].unique():
        df_emp = df[df['Employee'] == emp].sort_values('Date')
        
        # --- CHECK 1: Daily limit (12h) ---
        daily = df_emp.groupby('Date')['Hours_Worked'].sum()
        for dt, hours in daily.items():
            if hours > DAILY_LIMIT_HOURS:
                violations.append({
                    'Employee': emp,
                    'Date': dt,
                    'Violation': f'Przekroczony limit dzienny: {hours:.1f}h > {DAILY_LIMIT_HOURS}h',
                    'Severity': '🔴 Krytyczny',
                    'Category': 'Limit dzienny',
                })
        
        # --- CHECK 2: Weekly hard limit (60h) ---
        weekly = df_emp.groupby(['Year', 'Week_Number'])['Hours_Worked'].sum()
        for (yr, wk), hours in weekly.items():
            if hours > WEEKLY_HARD_LIMIT_HOURS:
                violations.append({
                    'Employee': emp,
                    'Date': f"Tydzień {wk}/{yr}",
                    'Violation': f'Przekroczony limit tygodniowy: {hours:.1f}h > {WEEKLY_HARD_LIMIT_HOURS}h',
                    'Severity': '🔴 Krytyczny',
                    'Category': 'Limit tygodniowy',
                })
        
        # --- CHECK 3: Rest between shifts (11h) ---
        if 'Start_Time' in df_emp.columns and 'End_Time' in df_emp.columns:
            sorted_days = df_emp.sort_values('Date')
            prev_end = None
            prev_date = None
            for _, row in sorted_days.iterrows():
                if pd.notna(row.get('Start_Time')) and prev_end is not None:
                    try:
                        current_start = datetime.combine(row['Date'].date(), 
                                        datetime.strptime(str(row['Start_Time']), '%H:%M').time())
                        previous_end = datetime.combine(prev_date, 
                                        datetime.strptime(str(prev_end), '%H:%M').time())
                        rest_hours = (current_start - previous_end).total_seconds() / 3600
                        if 0 < rest_hours < MIN_REST_BETWEEN_SHIFTS_HOURS:
                            violations.append({
                                'Employee': emp,
                                'Date': row['Date'],
                                'Violation': f'Za mało odpoczynku: {rest_hours:.1f}h < {MIN_REST_BETWEEN_SHIFTS_HOURS}h',
                                'Severity': '🟠 Ostrzeżenie',
                                'Category': 'Odpoczynek między zmianami',
                            })
                    except (ValueError, TypeError):
                        pass
                prev_end = row.get('End_Time')
                prev_date = row['Date'].date() if hasattr(row['Date'], 'date') else row['Date']
        
        # --- CHECK 4: Consecutive work days (max 6) ---
        work_dates = sorted(df_emp['Date'].dt.date.unique())
        consecutive = 1
        for i in range(1, len(work_dates)):
            if (work_dates[i] - work_dates[i-1]).days == 1:
                consecutive += 1
                if consecutive > MAX_CONSECUTIVE_WORK_DAYS:
                    violations.append({
                        'Employee': emp,
                        'Date': work_dates[i],
                        'Violation': f'{consecutive} dni pracy z rzędu (max {MAX_CONSECUTIVE_WORK_DAYS})',
                        'Severity': '🟠 Ostrzeżenie',
                        'Category': 'Dni z rzędu',
                    })
            else:
                consecutive = 1
    
    # --- CHECK 5: 16-week rolling average (48h) ---
    latest_date = df['Date'].max()
    start_period = latest_date - pd.Timedelta(weeks=ROLLING_PERIOD_WEEKS)
    recent = df[df['Date'] > start_period]
    
    avg_status = recent.groupby('Employee')['Hours_Worked'].sum().reset_index()
    avg_status['16_Week_Avg'] = (avg_status['Hours_Worked'] / ROLLING_PERIOD_WEEKS).round(2)
    avg_status['Over_48h'] = avg_status['16_Week_Avg'] > WEEKLY_AVG_LIMIT_HOURS
    avg_status = avg_status.rename(columns={'Hours_Worked': 'Total_Hours_Period'})
    
    for _, row in avg_status[avg_status['Over_48h']].iterrows():
        violations.append({
            'Employee': row['Employee'],
            'Date': f'Okres 16-tyg.',
            'Violation': f'Średnia {row["16_Week_Avg"]:.1f}h/tydz > {WEEKLY_AVG_LIMIT_HOURS}h',
            'Severity': '🔴 Krytyczny',
            'Category': 'Średnia 16-tyg.',
        })
    
    violations_df = pd.DataFrame(violations) if violations else pd.DataFrame()
    return violations_df, avg_status


def get_business_days_in_month(year, month):
    """Return the number of business days (Mon-Fri) in a given month, excluding Dutch holidays."""
    import calendar as cal
    first_day = date(year, month, 1)
    last_day = date(year, month, cal.monthrange(year, month)[1])
    count = 0
    d = first_day
    while d <= last_day:
        if d.weekday() < 5 and d not in ALL_HOLIDAYS:  # Mon-Fri, not a holiday
            count += 1
        d += timedelta(days=1)
    return count


def calculate_monthly_urenbank(df_emp_month, daily_cap=DAILY_PAID_CAP_HOURS):
    """Calculate urenbank for a calendar month.
    
    Logic (as actually used in Dutch greenhouse payroll):
    - Max paid per month = 9.6h × number of BUSINESS DAYS in that calendar month
      (e.g. May with 21 workdays → max 201.6h paid)
    - Total worked = sum of ALL hours in the month (including weekends)
    - If total worked > max paid → surplus goes to urenbank
    - If total worked < max paid → deficit (negative balance)
    
    The calculation happens once at end of month, NOT daily.
    """
    if df_emp_month.empty:
        return {'worked': 0, 'paid': 0, 'banked': 0, 'days_worked': 0,
                'business_days': 0, 'max_paid': 0}
    
    # Determine which calendar month this data belongs to
    first_date = df_emp_month['Date'].min()
    year = first_date.year
    month = first_date.month
    
    business_days = get_business_days_in_month(year, month)
    max_paid = daily_cap * business_days
    
    total_worked = df_emp_month['Hours_Worked'].sum()
    days_worked = df_emp_month['Date'].dt.date.nunique()
    
    paid = min(total_worked, max_paid)
    banked = total_worked - paid  # positive = surplus to urenbank
    
    return {
        'worked': round(total_worked, 2),
        'paid': round(paid, 2),
        'banked': round(banked, 2),
        'days_worked': days_worked,
        'business_days': business_days,
        'max_paid': round(max_paid, 2),
    }


def calculate_weekly_urenbank(df_emp_week, daily_cap=DAILY_PAID_CAP_HOURS):
    """Weekly summary for PDF — just shows worked hours.
    
    Note: urenbank is settled monthly, not weekly. Weekly rows in the PDF
    only show total worked. The monthly settlement appears in the summary rows.
    """
    total_worked = df_emp_week['Hours_Worked'].sum() if not df_emp_week.empty else 0.0
    return {
        'worked': round(total_worked, 2),
    }


# -------------------------------------------------------------------
# 5. Seasonal Analysis
# -------------------------------------------------------------------
def get_current_season(d=None):
    """Returns the current strawberry greenhouse season."""
    if d is None:
        d = date.today()
    month = d.month
    for season_name, info in STRAWBERRY_SEASONS.items():
        if month in info['months']:
            return season_name, info
    return 'Nieznany', {'intensity': 'unknown', 'color': '#999'}

def seasonal_workforce_analysis(df, employees):
    """Analyze workforce patterns by season."""
    df_copy = df.copy()
    df_copy['Month'] = df_copy['Date'].dt.month
    
    def get_season(month):
        for name, info in STRAWBERRY_SEASONS.items():
            if month in info['months']:
                return name
        return 'Inny'
    
    df_copy['Season'] = df_copy['Month'].apply(get_season)
    
    season_summary = df_copy.groupby('Season').agg(
        Avg_Daily_Hours=('Hours_Worked', 'mean'),
        Total_Hours=('Hours_Worked', 'sum'),
        Active_Workers=('Employee', 'nunique'),
        Work_Days=('Date', 'nunique'),
    ).round(2)
    
    return season_summary


# -------------------------------------------------------------------
# 6. Leave Entitlement Calculator
# -------------------------------------------------------------------
def calculate_leave_entitlement(employee_name, contract_hours, employees_dict):
    """Calculate legal leave entitlement per CAO."""
    if contract_hours <= 0:
        # 0-hour contracts: leave accrued based on hours actually worked
        return None  # Needs calculation from actual hours
    
    # Wettelijk verlof = 4x weekly hours per year
    annual_leave_hours = contract_hours * LEGAL_LEAVE_MULTIPLIER
    annual_leave_days = annual_leave_hours / (contract_hours / 5)  # Assuming 5-day week
    
    # Bovenwettelijk verlof (CAO Glastuinbouw extra) ~= 1-2 extra days
    extra_days = 2
    
    return {
        'wettelijk_hours': annual_leave_hours,
        'wettelijk_days': annual_leave_days,
        'bovenwettelijk_days': extra_days,
        'total_days': annual_leave_days + extra_days,
    }


# -------------------------------------------------------------------
# 7. PDF Report Generation
# -------------------------------------------------------------------
class PDFReport(FPDF):
    def header(self):
        self.set_font('helvetica', 'B', 14)
        self.cell(0, 10, 'Raport Czasu Pracy — Szklarnia Truskawkowa', 0, 1, 'C')
        self.set_font('helvetica', size=8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, 'Wygenerowano zgodnie z CAO Glastuinbouw', 0, 1, 'C')
        self.set_text_color(0, 0, 0)
        self.ln(3)

def generate_employee_pdf(employee_name, df, contract_hours):
    """Generate PDF timesheet with monthly urenbank settlement.
    
    Payment model:
    - Max paid per month = 9.6h × business days in that calendar month
      (e.g. 21 days → 201.6h, 22 days → 211.2h, 23 days → 220.8h)
    - At end of month: if total worked > max paid → surplus to urenbank
    - Urenbank hours are taken as time off later (czas za czas)
    """
    df_emp = df[df['Employee'] == employee_name].copy()
    if df_emp.empty:
        return None
    
    # Prepare weekly pivot for day-by-day display
    df_emp['Day_Name'] = df_emp['Date'].dt.day_name().str[:3]
    df_emp['YearMonth'] = df_emp['Date'].dt.to_period('M')
    
    daily_sum = df_emp.groupby(['Year', 'Week_Number', 'Day_Name'])['Hours_Worked'].sum().reset_index()
    pivot_df = daily_sum.pivot(index=['Year', 'Week_Number'], columns='Day_Name', values='Hours_Worked').reset_index()
    
    days_order = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    for day in days_order:
        if day not in pivot_df.columns:
            pivot_df[day] = 0.0
    pivot_df = pivot_df[['Year', 'Week_Number'] + days_order].fillna(0)
    pivot_df['Total_Worked'] = pivot_df[days_order].sum(axis=1)
    pivot_df = pivot_df.sort_values(by=['Year', 'Week_Number'])
    
    # Pre-calculate monthly settlements
    monthly_settlements = {}
    cumulative_bank = 0.0
    for ym, group in df_emp.groupby('YearMonth'):
        ub = calculate_monthly_urenbank(group, DAILY_PAID_CAP_HOURS)
        cumulative_bank += ub['banked']
        monthly_settlements[str(ym)] = {**ub, 'cumulative': round(cumulative_bank, 2)}
    
    # Figure out which month each week primarily belongs to
    week_months = {}
    for (yr, wk), grp in df_emp.groupby(['Year', 'Week_Number']):
        # Use the most common month in this week's data
        month_mode = grp['Date'].dt.month.mode().iloc[0]
        year_for_month = grp[grp['Date'].dt.month == month_mode]['Date'].dt.year.mode().iloc[0]
        week_months[(yr, wk)] = f"{year_for_month}-{month_mode:02d}"
    
    pdf = PDFReport(orientation='L')
    pdf.add_page()
    
    # Employee info
    pdf.set_font("helvetica", 'B', 12)
    pdf.cell(0, 8, f"Pracownik: {employee_name}", 0, 1)
    pdf.set_font("helvetica", size=10)
    contract_text = f"{contract_hours}h/tydzien" if contract_hours > 0 else "Kontrakt 0-godzin (nul-uren)"
    pdf.cell(0, 6, f"Typ kontraktu: {contract_text}", 0, 1)
    pdf.cell(0, 6, f"Rozliczenie: max {DAILY_PAID_CAP_HOURS}h x dni robocze w miesiacu | Nadwyzka -> urenbank", 0, 1)
    pdf.cell(0, 6, f"Data generowania: {date.today().strftime('%d-%m-%Y')}", 0, 1)
    pdf.ln(5)
    
    # Table headers
    headers = ['Rok', 'Tydz', 'Pon', 'Wt', 'Sr', 'Czw', 'Pt', 'Sob', 'Ndz', 'Suma tyg.']
    col_w = [14, 12, 19, 19, 19, 19, 19, 19, 19, 24]
    total_table_w = sum(col_w)
    
    pdf.set_font("helvetica", 'B', 8)
    pdf.set_fill_color(45, 55, 72)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 9, h, border=1, align='C', fill=True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0)
    
    pdf.set_font("helvetica", size=8)
    
    prev_month_key = None
    
    for _, row in pivot_df.iterrows():
        yr = int(row['Year'])
        wk = int(row['Week_Number'])
        current_month_key = week_months.get((yr, wk), '')
        
        # Insert monthly settlement row when month changes
        if prev_month_key is not None and current_month_key != prev_month_key and prev_month_key in monthly_settlements:
            ms = monthly_settlements[prev_month_key]
            pdf.set_font("helvetica", 'B', 8)
            pdf.set_fill_color(230, 240, 255)
            
            label = f"MIESIAC {prev_month_key}: przepr. {ms['worked']:.1f}h | " \
                    f"max wyplata ({ms['business_days']} dni x {DAILY_PAID_CAP_HOURS}h) = {ms['max_paid']:.1f}h | " \
                    f"do banku: {ms['banked']:+.1f}h | saldo: {ms['cumulative']:+.1f}h"
            
            pdf.cell(total_table_w, 8, label, border=1, align='C', fill=True)
            pdf.ln()
            pdf.set_font("helvetica", size=8)
        
        prev_month_key = current_month_key
        
        # Weekly detail row
        pdf.cell(col_w[0], 7, str(yr), border=1, align='C')
        pdf.cell(col_w[1], 7, str(wk), border=1, align='C')
        
        for i, day in enumerate(days_order):
            val = row[day]
            txt = f"{val:.1f}" if val > 0 else "-"
            if day == 'Sat' and val > 0:
                pdf.set_fill_color(255, 248, 230)
                pdf.cell(col_w[i+2], 7, txt, border=1, align='C', fill=True)
            elif day == 'Sun' and val > 0:
                pdf.set_fill_color(255, 235, 235)
                pdf.cell(col_w[i+2], 7, txt, border=1, align='C', fill=True)
            else:
                pdf.cell(col_w[i+2], 7, txt, border=1, align='C')
        
        # Weekly total
        worked = row['Total_Worked']
        pdf.set_font("helvetica", 'B', 8)
        pdf.cell(col_w[9], 7, f"{worked:.1f}", border=1, align='C')
        pdf.set_font("helvetica", size=8)
        pdf.ln()
    
    # Final month settlement (for the last month in the data)
    if prev_month_key and prev_month_key in monthly_settlements:
        ms = monthly_settlements[prev_month_key]
        pdf.set_font("helvetica", 'B', 8)
        pdf.set_fill_color(230, 240, 255)
        label = f"MIESIAC {prev_month_key}: przepr. {ms['worked']:.1f}h | " \
                f"max wyplata ({ms['business_days']} dni x {DAILY_PAID_CAP_HOURS}h) = {ms['max_paid']:.1f}h | " \
                f"do banku: {ms['banked']:+.1f}h | saldo: {ms['cumulative']:+.1f}h"
        pdf.cell(total_table_w, 8, label, border=1, align='C', fill=True)
        pdf.ln()
    
    # Grand summary
    pdf.ln(5)
    pdf.set_font("helvetica", 'B', 11)
    
    total_worked = df_emp['Hours_Worked'].sum()
    total_paid = sum(ms['paid'] for ms in monthly_settlements.values())
    final_balance = cumulative_bank
    
    pdf.cell(0, 8, f"RAZEM: przepracowano {total_worked:.1f}h | "
                    f"wyplacono {total_paid:.1f}h | "
                    f"saldo urenbank: {final_balance:+.1f}h", 0, 1, 'R')
    
    if final_balance > 0:
        equiv_days = final_balance / DAILY_PAID_CAP_HOURS
        pdf.set_font("helvetica", size=9)
        pdf.set_text_color(0, 100, 180)
        pdf.cell(0, 7, f"= {equiv_days:.1f} dni do odebrania z urenbank", 0, 1, 'R')
        pdf.set_text_color(0, 0, 0)
    
    return bytes(pdf.output())


# -------------------------------------------------------------------
# 8. Main Application UI
# -------------------------------------------------------------------
def main():
    init_leave_data()
    
    # --- SIDEBAR ---
    st.sidebar.markdown("## 🍓 Szklarnia HR")
    st.sidebar.caption("System zarządzania czasem pracy")
    
    st.sidebar.markdown("---")
    st.sidebar.header("📂 Import danych")
    uploaded_file = st.sidebar.file_uploader("Prześlij plik z Duinkier (CSV/Excel)", type=['csv', 'xlsx'])
    
    if uploaded_file is not None:
        raw_data, employees = process_uploaded_file(uploaded_file)
        if raw_data is not None:
            st.sidebar.success("✅ Plik wczytany!")
    else:
        raw_data, employees = load_dummy_data()
        st.sidebar.info("Pokazuję dane testowe. Prześlij plik, aby zobaczyć realne dane.")
    
    if raw_data is None or raw_data.empty:
        st.stop()

    # Sidebar: Employee management
    st.sidebar.markdown("---")
    st.sidebar.header("👤 Pracownicy")
    
    # Allow editing contract types in sidebar
    if 'employee_contracts' not in st.session_state:
        st.session_state.employee_contracts = {}
        for emp, info in employees.items():
            st.session_state.employee_contracts[emp] = {
                'contract_type': info.get('contract', 'nul_uren'),
                'contract_hours': info.get('hours', 0.0),
            }
    
    employee_list = list(raw_data['Employee'].unique())
    
    # --- MAIN TABS ---
    tab_dashboard, tab_compliance, tab_leave, tab_seasonal, tab_export = st.tabs([
        "📊 Dashboard", "⚖️ Zgodność CAO", "🏖️ Urlopy i Chorobowe",
        "🍓 Sezonowość", "📄 Eksport PDF"
    ])
    
    # =================================================================
    # TAB 1: Dashboard
    # =================================================================
    with tab_dashboard:
        current_season, season_info = get_current_season()
        
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, {season_info['color']}33, {season_info['color']}11); 
                    padding: 16px 24px; border-radius: 12px; border-left: 5px solid {season_info['color']}; margin-bottom: 20px;">
            <span style="font-size: 1.1em; font-weight: 600;">Aktualny sezon:</span>
            <span class="season-badge" style="background-color: {season_info['color']};">{current_season}</span>
            <span style="margin-left: 12px; color: #666;">Intensywność: <strong>{season_info['intensity'].upper()}</strong></span>
        </div>
        """, unsafe_allow_html=True)
        
        violations_df, avg_status = check_full_compliance(raw_data)
        
        # Metrics row
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Pracownicy aktywni", len(employee_list))
        c2.metric("Rekordy łącznie", f"{len(raw_data):,}")
        
        critical_count = len(violations_df[violations_df['Severity'] == '🔴 Krytyczny']) if not violations_df.empty else 0
        warning_count = len(violations_df[violations_df['Severity'] == '🟠 Ostrzeżenie']) if not violations_df.empty else 0
        c3.metric("Naruszenia krytyczne", critical_count, delta=None)
        c4.metric("Ostrzeżenia", warning_count, delta=None)
        
        st.markdown("---")
        
        # Quick overview: hours per employee this week
        st.subheader("Godziny w bieżącym tygodniu")
        today = pd.Timestamp(date.today())
        start_of_week = today - pd.Timedelta(days=today.dayofweek)
        this_week = raw_data[(raw_data['Date'] >= start_of_week) & (raw_data['Date'] <= today)]
        
        if not this_week.empty:
            weekly_summary = this_week.groupby('Employee')['Hours_Worked'].sum().reset_index()
            weekly_summary.columns = ['Pracownik', 'Godziny']
            weekly_summary = weekly_summary.sort_values('Godziny', ascending=False)
            
            # Simple bar visualization
            for _, row in weekly_summary.iterrows():
                pct = min(row['Godziny'] / WEEKLY_HARD_LIMIT_HOURS * 100, 100)
                color = '#38a169' if row['Godziny'] <= 40 else '#dd6b20' if row['Godziny'] <= 50 else '#e53e3e'
                emp_contract = st.session_state.employee_contracts.get(row['Pracownik'], {})
                contract_label = CONTRACT_TYPES.get(emp_contract.get('contract_type', 'nul_uren'), 'Nieznany')
                
                st.markdown(f"""
                <div style="margin: 6px 0;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
                        <span><strong>{row['Pracownik']}</strong> <small style="color:#888">({contract_label})</small></span>
                        <span style="font-weight:600; color:{color}">{row['Godziny']:.1f}h</span>
                    </div>
                    <div style="background:#edf2f7; border-radius:6px; height:10px; overflow:hidden;">
                        <div style="width:{pct}%; background:{color}; height:100%; border-radius:6px; transition: width 0.5s;"></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Brak danych na bieżący tydzień.")
        
        st.markdown("---")
        
        # Recent violations
        if not violations_df.empty:
            st.subheader("Ostatnie naruszenia")
            st.dataframe(
                violations_df.sort_values('Severity', ascending=True).head(15),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.markdown("""
            <div class="alert-card alert-green">
                <strong>✅ Wszystko w porządku!</strong> Brak naruszeń w analizowanym okresie.
            </div>
            """, unsafe_allow_html=True)
    
    # =================================================================
    # TAB 2: CAO Compliance
    # =================================================================
    with tab_compliance:
        st.header("⚖️ Pełna kontrola zgodności — CAO Glastuinbouw")
        
        st.markdown("""
        <div class="alert-card alert-blue">
            <strong>ℹ️ Kontrolowane zasady:</strong><br>
            • Maksymalnie 12 godzin dziennie<br>
            • Maksymalnie 60 godzin tygodniowo (bezwzględny limit)<br>
            • Średnia ≤ 48h/tydzień w okresie krocząnym 16 tygodni<br>
            • Minimum 11 godzin odpoczynku między zmianami<br>
            • Maksymalnie 6 dni pracy z rzędu<br>
            • Wypłata max. {DAILY_PAID_CAP_HOURS}h/dzień — nadwyżka → urenbank (czas za czas)
        </div>
        """, unsafe_allow_html=True)
        
        selected_emp_compliance = st.selectbox(
            "Sprawdź pracownika:", ['Wszyscy'] + employee_list, key='compliance_emp'
        )
        
        if selected_emp_compliance != 'Wszyscy':
            check_data = raw_data[raw_data['Employee'] == selected_emp_compliance]
        else:
            check_data = raw_data
        
        violations_df_filtered, avg_status_filtered = check_full_compliance(check_data)
        
        if not violations_df_filtered.empty:
            # Group by category
            st.subheader("Naruszenia według kategorii")
            for cat in violations_df_filtered['Category'].unique():
                cat_df = violations_df_filtered[violations_df_filtered['Category'] == cat]
                severity = cat_df.iloc[0]['Severity']
                with st.expander(f"{severity} {cat} — {len(cat_df)} przypadków"):
                    st.dataframe(cat_df[['Employee', 'Date', 'Violation']], use_container_width=True, hide_index=True)
        else:
            st.success("✅ Brak naruszeń dla wybranego zakresu!")
        
        # 16-week average table
        st.subheader(f"📊 Średnia krocząca 16-tygodniowa")
        if not avg_status_filtered.empty:
            def style_avg(row):
                if row.get('Over_48h', False):
                    return ['background-color: #ffcccc'] * len(row)
                return [''] * len(row)
            st.dataframe(
                avg_status_filtered.style.apply(style_avg, axis=1),
                use_container_width=True, hide_index=True,
            )
        
        # Urenbank overview
        st.subheader("🏦 Urenbank — rozliczenie miesięczne")
        st.caption(f"Wypłata max = {DAILY_PAID_CAP_HOURS}h × liczba dni roboczych w miesiącu. Nadwyżka → urenbank (czas za czas).")
        
        if selected_emp_compliance != 'Wszyscy':
            emp_data = raw_data[raw_data['Employee'] == selected_emp_compliance]
            
            if not emp_data.empty:
                emp_data_copy = emp_data.copy()
                emp_data_copy['YearMonth'] = emp_data_copy['Date'].dt.to_period('M')
                
                urenbank_data = []
                running_balance = 0.0
                for ym, group in emp_data_copy.groupby('YearMonth'):
                    ub = calculate_monthly_urenbank(group, DAILY_PAID_CAP_HOURS)
                    running_balance += ub['banked']
                    urenbank_data.append({
                        'Miesiąc': str(ym),
                        'Dni pracy': ub['days_worked'],
                        'Dni robocze mies.': ub['business_days'],
                        'Przepracowano': ub['worked'],
                        f'Max wypłata': f"{ub['business_days']}×{DAILY_PAID_CAP_HOURS}={ub['max_paid']:.1f}",
                        'Wypłacono': ub['paid'],
                        'Do banku': ub['banked'],
                        'Saldo urenbank': round(running_balance, 2),
                    })
                
                ub_df = pd.DataFrame(urenbank_data)
                
                def style_urenbank(row):
                    if row['Do banku'] > 0:
                        return ['background-color: #ebf8ff'] * len(row)
                    elif row['Do banku'] < 0:
                        return ['background-color: #fff5f5'] * len(row)
                    return [''] * len(row)
                
                st.dataframe(
                    ub_df.style.apply(style_urenbank, axis=1),
                    use_container_width=True, hide_index=True,
                )
                
                total_banked = running_balance
                equiv_days = total_banked / DAILY_PAID_CAP_HOURS if total_banked > 0 else 0
                
                ub_c1, ub_c2, ub_c3 = st.columns(3)
                ub_c1.metric("Saldo urenbank", f"{total_banked:+.1f}h")
                ub_c2.metric("= dni wolnych", f"{equiv_days:.1f}")
                ub_c3.metric("Średnia cap/mies.", f"{DAILY_PAID_CAP_HOURS}h × ~21-22 dni")
        else:
            # Summary for all employees — also monthly
            all_urenbank = []
            for emp in employee_list:
                emp_data = raw_data[raw_data['Employee'] == emp]
                if emp_data.empty:
                    continue
                emp_copy = emp_data.copy()
                emp_copy['YearMonth'] = emp_copy['Date'].dt.to_period('M')
                
                total_banked = 0.0
                total_worked = 0.0
                total_paid = 0.0
                for ym, group in emp_copy.groupby('YearMonth'):
                    ub = calculate_monthly_urenbank(group, DAILY_PAID_CAP_HOURS)
                    total_banked += ub['banked']
                    total_worked += ub['worked']
                    total_paid += ub['paid']
                
                all_urenbank.append({
                    'Pracownik': emp,
                    'Przepracowano': round(total_worked, 1),
                    'Wypłacono': round(total_paid, 1),
                    'Urenbank': round(total_banked, 1),
                    'Dni do odebrania': round(total_banked / DAILY_PAID_CAP_HOURS, 1) if total_banked > 0 else 0,
                })
            
            if all_urenbank:
                st.dataframe(
                    pd.DataFrame(all_urenbank).sort_values('Urenbank', ascending=False),
                    use_container_width=True, hide_index=True,
                )
    
    # =================================================================
    # TAB 3: Leave & Sick Tracking
    # =================================================================
    with tab_leave:
        st.header("🏖️ Urlopy i Chorobowe")
        
        leave_col, sick_col = st.columns(2)
        
        with leave_col:
            st.subheader("📅 Rejestracja urlopu")
            with st.form("leave_form"):
                leave_emp = st.selectbox("Pracownik", employee_list, key='leave_emp')
                leave_type = st.selectbox("Typ", [
                    'Wettelijk verlof (ustawowy)',
                    'Bovenwettelijk verlof (dodatkowy CAO)',
                    'Bijzonder verlof (okolicznościowy)',
                    'Onbetaald verlof (bezpłatny)',
                ])
                lc1, lc2 = st.columns(2)
                leave_start = lc1.date_input("Od", value=date.today())
                leave_end = lc2.date_input("Do", value=date.today() + timedelta(days=5))
                leave_notes = st.text_input("Uwagi", placeholder="np. wakacje, ślub...")
                
                if st.form_submit_button("➕ Dodaj urlop"):
                    add_leave_record(leave_emp, leave_start, leave_end, leave_type, leave_notes)
                    st.success(f"Urlop dla {leave_emp} zapisany!")
            
            # Leave entitlements
            st.markdown("---")
            st.subheader("📋 Uprawnienia urlopowe")
            for emp in employee_list:
                emp_c = st.session_state.employee_contracts.get(emp, {})
                c_hrs = emp_c.get('contract_hours', 0.0)
                entitlement = calculate_leave_entitlement(emp, c_hrs, employees)
                
                if entitlement:
                    used = sum(r['Days'] for r in st.session_state.leave_records if r['Employee'] == emp)
                    remaining = entitlement['total_days'] - used
                    
                    color = '#38a169' if remaining > 5 else '#dd6b20' if remaining > 0 else '#e53e3e'
                    st.markdown(f"""
                    <div style="padding:8px 12px; background:#f7fafc; border-radius:8px; margin:4px 0; border-left:3px solid {color};">
                        <strong>{emp}</strong> — {entitlement['wettelijk_days']:.0f} + {entitlement['bovenwettelijk_days']} = 
                        <strong>{entitlement['total_days']:.0f} dni</strong> | 
                        Wykorzystano: {used} | <span style="color:{color}; font-weight:600;">Pozostało: {remaining:.0f}</span>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # 0-hour contract: calculate from actual hours
                    emp_hours = raw_data[raw_data['Employee'] == emp]['Hours_Worked'].sum()
                    accrued_hours = emp_hours * (LEGAL_LEAVE_MULTIPLIER / 52)  # proportional
                    used_h = sum(r['Days'] * 8 for r in st.session_state.leave_records if r['Employee'] == emp)
                    
                    st.markdown(f"""
                    <div style="padding:8px 12px; background:#f7fafc; border-radius:8px; margin:4px 0; border-left:3px solid #3182ce;">
                        <strong>{emp}</strong> <small>(0-uren)</small> — Opgebouwde uren: <strong>{accrued_hours:.1f}h</strong> | 
                        Wykorzystano: {used_h:.0f}h
                    </div>
                    """, unsafe_allow_html=True)
        
        with sick_col:
            st.subheader("🤒 Rejestracja chorobowego")
            with st.form("sick_form"):
                sick_emp = st.selectbox("Pracownik", employee_list, key='sick_emp')
                sc1, sc2 = st.columns(2)
                sick_start = sc1.date_input("Pierwszy dzień choroby", value=date.today())
                sick_end = sc2.date_input("Powrót (zostaw puste jeśli trwa)", value=None)
                sick_notes = st.text_input("Uwagi", placeholder="np. ból pleców, przeziębienie...", key='sick_notes')
                
                if st.form_submit_button("➕ Zarejestruj chorobowe"):
                    add_sick_record(sick_emp, sick_start, sick_end, sick_end is not None, sick_notes)
                    st.success(f"Chorobowe dla {sick_emp} zarejestrowane.")
            
            # Sick leave overview
            st.markdown("---")
            st.subheader("📊 Wskaźnik absencji (Verzuimpercentage)")
            
            # Calculate absence rate per employee
            total_possible_days = len(raw_data['Date'].dt.date.unique())
            for emp in employee_list:
                sick_days = sum(
                    (r.get('End_Date', date.today()) or date.today() - r['Start_Date']).days + 1
                    if isinstance(r.get('End_Date'), date) else
                    (date.today() - r['Start_Date']).days + 1
                    for r in st.session_state.sick_records 
                    if r['Employee'] == emp
                )
                worked_days = len(raw_data[raw_data['Employee'] == emp]['Date'].dt.date.unique())
                rate = (sick_days / max(worked_days, 1)) * 100
                
                bar_color = '#38a169' if rate < 4 else '#dd6b20' if rate < 8 else '#e53e3e'
                st.markdown(f"""
                <div style="padding:6px 12px; margin:3px 0;">
                    <div style="display:flex; justify-content:space-between;">
                        <span>{emp}</span>
                        <span style="color:{bar_color}; font-weight:600;">{rate:.1f}%</span>
                    </div>
                    <div style="background:#edf2f7; border-radius:4px; height:6px;">
                        <div style="width:{min(rate*5, 100)}%; background:{bar_color}; height:100%; border-radius:4px;"></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            st.caption("Średni wskaźnik w ogrodnictwie NL: ~4-5%. Powyżej 8% wymaga interwencji Arbodienst.")
        
        # Leave records table
        if st.session_state.leave_records:
            st.markdown("---")
            st.subheader("📋 Zarejestrowane urlopy")
            st.dataframe(pd.DataFrame(st.session_state.leave_records), use_container_width=True, hide_index=True)
        
        if st.session_state.sick_records:
            st.subheader("🤒 Zarejestrowane chorobowe")
            st.dataframe(pd.DataFrame(st.session_state.sick_records), use_container_width=True, hide_index=True)
    
    # =================================================================
    # TAB 4: Seasonal Analysis
    # =================================================================
    with tab_seasonal:
        st.header("🍓 Analiza sezonowa — Szklarnia truskawkowa")
        
        # Season calendar
        st.subheader("Kalendarz sezonów")
        months_pl = ['Sty', 'Lut', 'Mar', 'Kwi', 'Maj', 'Cze', 'Lip', 'Sie', 'Wrz', 'Paź', 'Lis', 'Gru']
        
        season_html = '<div style="display:flex; gap:4px; margin:12px 0;">'
        for i, month_name in enumerate(months_pl, 1):
            color = '#ccc'
            label = ''
            for sname, sinfo in STRAWBERRY_SEASONS.items():
                if i in sinfo['months']:
                    color = sinfo['color']
                    label = sname
                    break
            current = '⬇️' if i == date.today().month else ''
            season_html += f"""
            <div style="flex:1; background:{color}22; border:2px solid {color}; border-radius:8px; 
                        padding:8px 4px; text-align:center; min-width:60px;">
                <div style="font-weight:700; font-size:0.9em;">{month_name}</div>
                <div style="font-size:0.7em; color:#555; margin-top:2px;">{label.split('/')[0].split('(')[0].strip()[:10]}</div>
                <div>{current}</div>
            </div>"""
        season_html += '</div>'
        st.markdown(season_html, unsafe_allow_html=True)
        
        # Season legend
        legend_html = '<div style="display:flex; gap:16px; margin:8px 0; flex-wrap:wrap;">'
        for sname, sinfo in STRAWBERRY_SEASONS.items():
            legend_html += f'<span class="season-badge" style="background-color:{sinfo["color"]};">{sname}</span>'
        legend_html += '</div>'
        st.markdown(legend_html, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Workforce by season
        st.subheader("Zapotrzebowanie na pracowników wg sezonu")
        season_summary = seasonal_workforce_analysis(raw_data, employees)
        
        if not season_summary.empty:
            st.dataframe(season_summary, use_container_width=True)
        
        # Monthly hours chart
        st.subheader("📈 Średnie godziny dziennie — trend miesięczny")
        monthly = raw_data.copy()
        monthly['Month'] = monthly['Date'].dt.to_period('M').astype(str)
        monthly_avg = monthly.groupby('Month')['Hours_Worked'].mean().reset_index()
        monthly_avg.columns = ['Miesiąc', 'Śr. godzin/dzień']
        st.bar_chart(monthly_avg.set_index('Miesiąc'))
        
        # Staffing alerts
        st.subheader("⚠️ Alerty sezonowe")
        current_month = date.today().month
        
        # Look ahead 2 months
        upcoming_month = (current_month % 12) + 1
        for sname, sinfo in STRAWBERRY_SEASONS.items():
            if upcoming_month in sinfo['months'] and sinfo['intensity'] == 'high':
                st.markdown(f"""
                <div class="alert-card alert-orange">
                    <strong>⚠️ Zbliża się sezon: {sname}</strong><br>
                    Za ok. 4-8 tygodni rozpoczyna się okres wysokiej intensywności. 
                    Sprawdź, czy masz wystarczającą liczbę pracowników (zwłaszcza 0-urencontracten).
                    Zalecana minimalna załoga na zbiory: 1 osoba na każde ~500m² uprawy.
                </div>
                """, unsafe_allow_html=True)
        
        # 0-hour contract utilization
        st.subheader("📊 Wykorzystanie kontraktów 0-godzinnych")
        nul_uren_emps = [e for e, c in st.session_state.employee_contracts.items() 
                         if c.get('contract_type') == 'nul_uren']
        
        if nul_uren_emps:
            for emp in nul_uren_emps:
                emp_data = raw_data[raw_data['Employee'] == emp]
                if not emp_data.empty:
                    total_h = emp_data['Hours_Worked'].sum()
                    avg_weekly = total_h / max(emp_data['Date'].dt.isocalendar().week.nunique(), 1)
                    active_weeks = emp_data.groupby([emp_data['Date'].dt.isocalendar().year, 
                                                     emp_data['Date'].dt.isocalendar().week]).ngroups
                    
                    st.markdown(f"""
                    <div style="padding:8px 14px; background:#f0f4f8; border-radius:8px; margin:4px 0;">
                        <strong>{emp}</strong> — Łącznie: {total_h:.0f}h | 
                        Śr. tygodniowo: {avg_weekly:.1f}h | 
                        Aktywne tygodnie: {active_weeks}
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("Brak pracowników na kontraktach 0-godzinnych w danych.")
    
    # =================================================================
    # TAB 5: PDF Export
    # =================================================================
    with tab_export:
        st.header("📄 Eksport raportów PDF")
        
        export_emp = st.selectbox("Wybierz pracownika", employee_list, key='export_emp')
        
        emp_contract = st.session_state.employee_contracts.get(export_emp, {})
        
        ec1, ec2 = st.columns(2)
        contract_type = ec1.selectbox(
            "Typ kontraktu",
            list(CONTRACT_TYPES.keys()),
            format_func=lambda x: CONTRACT_TYPES[x],
            index=list(CONTRACT_TYPES.keys()).index(emp_contract.get('contract_type', 'nul_uren')),
            key='export_contract_type'
        )
        
        default_hours = emp_contract.get('contract_hours', 0.0)
        if contract_type == 'nul_uren':
            contract_hours = 0.0
            ec2.info("Kontrakt 0-godzin — brak stałych godzin")
        else:
            contract_hours = ec2.number_input(
                "Godziny tygodniowo",
                min_value=0.0, max_value=60.0,
                value=default_hours if default_hours > 0 else 38.0,
                step=0.5,
                key='export_hours'
            )
        
        # Update session state
        st.session_state.employee_contracts[export_emp] = {
            'contract_type': contract_type,
            'contract_hours': contract_hours,
        }
        
        # Date range filter
        st.markdown("**Zakres dat:**")
        dc1, dc2 = st.columns(2)
        min_date = raw_data['Date'].min().date()
        max_date = raw_data['Date'].max().date()
        date_from = dc1.date_input("Od", value=min_date, min_value=min_date, max_value=max_date)
        date_to = dc2.date_input("Do", value=max_date, min_value=min_date, max_value=max_date)
        
        filtered_data = raw_data[
            (raw_data['Date'] >= pd.Timestamp(date_from)) & 
            (raw_data['Date'] <= pd.Timestamp(date_to))
        ]
        
        if st.button("🔄 Generuj PDF", type="primary"):
            pdf_bytes = generate_employee_pdf(export_emp, filtered_data, contract_hours)
            if pdf_bytes:
                st.success("PDF gotowy do pobrania!")
                st.download_button(
                    label="📥 Pobierz raport PDF",
                    data=pdf_bytes,
                    file_name=f"Timesheet_{export_emp.replace(' ', '_')}_{date_from}_{date_to}.pdf",
                    mime="application/pdf",
                )
            else:
                st.warning("Brak danych dla tego pracownika w wybranym zakresie.")
        
        # Quick summary for selected employee
        st.markdown("---")
        st.subheader(f"Podgląd — {export_emp}")
        emp_preview = filtered_data[filtered_data['Employee'] == export_emp]
        if not emp_preview.empty:
            pc1, pc2, pc3 = st.columns(3)
            pc1.metric("Łączne godziny", f"{emp_preview['Hours_Worked'].sum():.1f}h")
            pc2.metric("Śr. dziennie", f"{emp_preview['Hours_Worked'].mean():.1f}h")
            pc3.metric("Dni pracy", len(emp_preview['Date'].dt.date.unique()))
            
            weekly_preview = emp_preview.groupby(['Year', 'Week_Number'])['Hours_Worked'].sum().reset_index()
            weekly_preview = weekly_preview.sort_values(['Year', 'Week_Number'])
            weekly_preview['Label'] = weekly_preview.apply(lambda r: f"{int(r['Year'])}-W{int(r['Week_Number']):02d}", axis=1)
            weekly_preview = weekly_preview.set_index('Label')
            st.bar_chart(weekly_preview['Hours_Worked'])


if __name__ == "__main__":
    main()
