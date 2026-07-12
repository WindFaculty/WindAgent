import numpy as np
import pandas as pd
from typing import Tuple

def generate_synthetic_data(num_users: int = 5000, random_state: int = 42) -> pd.DataFrame:
    """
    Generates a synthetic dataset representing user behavior, demographics, 
    transactional history, and a target 'user_score' (continuous) and 'risk_class' (categorical).
    """
    np.random.seed(random_state)
    
    # Demographics
    age = np.random.randint(18, 70, size=num_users)
    income = np.random.lognormal(mean=10.5, sigma=0.5, size=num_users)  # Median around $36k with right skew
    occupation_category = np.random.choice(
        ["Student", "Self-Employed", "Employed", "Unemployed", "Retired"],
        size=num_users,
        p=[0.15, 0.20, 0.50, 0.10, 0.05]
    )
    
    # Engagement metrics
    days_active = np.random.randint(1, 365, size=num_users)
    app_opens_last_30d = np.random.negative_binomial(n=10, p=0.4, size=num_users) # Right-skewed engagement count
    has_premium = np.random.choice([0, 1], size=num_users, p=[0.85, 0.15])
    device_type = np.random.choice(
        ["iOS", "Android", "Web"],
        size=num_users,
        p=[0.45, 0.45, 0.10]
    )
    
    # Transactional history
    completed_transactions = np.random.poisson(lam=15, size=num_users)
    # Failed transactions tend to decrease with tenure/income
    failed_ratio = np.random.beta(a=1, b=5, size=num_users)
    failed_transactions = np.round(completed_transactions * failed_ratio).astype(int)
    
    average_transaction_value = np.random.exponential(scale=50.0, size=num_users) + 5.0
    
    # Customer support
    customer_support_tickets = np.random.poisson(lam=1.5, size=num_users)
    
    # Create DataFrame
    df = pd.DataFrame({
        "user_id": [f"USR_{i:06d}" for i in range(num_users)],
        "age": age,
        "income": income,
        "occupation_category": occupation_category,
        "days_active": days_active,
        "app_opens_last_30d": app_opens_last_30d,
        "has_premium": has_premium,
        "device_type": device_type,
        "completed_transactions": completed_transactions,
        "failed_transactions": failed_transactions,
        "average_transaction_value": average_transaction_value,
        "customer_support_tickets": customer_support_tickets
    })
    
    # Inject missing values to make it realistic for preprocessing
    # 5% missingness in income and average_transaction_value
    income_mask = np.random.rand(num_users) < 0.05
    df.loc[income_mask, "income"] = np.nan
    
    txn_mask = np.random.rand(num_users) < 0.03
    df.loc[txn_mask, "average_transaction_value"] = np.nan
    
    # Generate Synthetic User Score (Target)
    # We create a deterministic base score and add noise
    # Base formula translates to credit-like score (300 to 850)
    base_score = 600.0
    
    # Normalize inputs for target generation (using median/approximate ranges)
    norm_income = np.clip((df["income"].fillna(36000) - 10000) / 100000, 0, 1)
    norm_days = df["days_active"] / 365.0
    norm_app_opens = np.clip(df["app_opens_last_30d"] / 50.0, 0, 1)
    norm_failed = np.clip(df["failed_transactions"] / (df["completed_transactions"] + 1), 0, 1)
    
    # Compute base component weights
    score_delta = (
        norm_income * 100.0 +
        norm_days * 80.0 +
        norm_app_opens * 40.0 +
        df["has_premium"] * 50.0 -
        norm_failed * 120.0 -
        (df["customer_support_tickets"] * 15.0)
    )
    
    # Add noise
    noise = np.random.normal(loc=0.0, scale=25.0, size=num_users)
    
    final_score = base_score + score_delta + noise
    # Clip between 300 and 850
    df["user_score"] = np.clip(final_score, 300.0, 850.0)
    
    # Convert to classes
    # 300-580: High Risk (0)
    # 580-700: Medium Risk (1)
    # 700-850: Low Risk (2)
    def categorize_risk(score):
        if score < 580:
            return 0  # High Risk
        elif score < 700:
            return 1  # Medium Risk
        else:
            return 2  # Low Risk
            
    df["risk_class"] = df["user_score"].apply(categorize_risk)
    
    return df

if __name__ == "__main__":
    df = generate_synthetic_data(10)
    print(df.head())
    print(df.info())
