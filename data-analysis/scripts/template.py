import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt

# Set aesthetics
sns.set_theme(style="whitegrid")
plt.rcParams['figure.figsize'] = (10, 6)

def load_and_inspect(filepath):
    """
    Loads data and performs initial inspection.
    """
    print(f"--- Loading {filepath} ---")
    try:
        df = pd.read_csv(filepath) # Try default utf-8
    except UnicodeDecodeError:
        df = pd.read_csv(filepath, encoding='latin1') # Fallback
        
    print("\n[Shape]:", df.shape)
    print("\n[Columns]:", df.columns.tolist())
    print("\n[Types]:")
    print(df.dtypes)
    print("\n[Missing Values]:")
    print(df.isnull().sum()[df.isnull().sum() > 0])
    
    print("\n[Preview]:")
    print(df.head())
    return df

def analyze_numerical(df, column):
    """
    Analyzes a numerical column with stats and visualization.
    """
    print(f"\n--- Analyzing Numerical: {column} ---")
    desc = df[column].describe()
    print(desc)
    
    plt.figure()
    sns.histplot(df[column], kde=True)
    plt.title(f"Distribution of {column}")
    plt.xlabel(column)
    plt.ylabel("Frequency")
    plt.tight_layout()
    # plt.savefig(f"dist_{column}.png") # Uncomment to save
    plt.show()

def analyze_categorical(df, column):
    """
    Analyzes a categorical column.
    """
    print(f"\n--- Analyzing Categorical: {column} ---")
    counts = df[column].value_counts()
    print(counts.head(10))
    
    plt.figure()
    sns.countplot(y=column, data=df, order=counts.index[:10])
    plt.title(f"Top 10 Categories in {column}")
    plt.xlabel("Count")
    plt.ylabel(column)
    plt.tight_layout()
    plt.show()

# Example Usage
if __name__ == "__main__":
    # Create dummy data if no file provided
    data = {
        'Category': np.random.choice(['A', 'B', 'C'], 100),
        'Value': np.random.normal(50, 15, 100),
        'Date': pd.date_range(start='2023-01-01', periods=100)
    }
    df = pd.DataFrame(data)
    
    print("Running Template Analysis...")
    analyze_numerical(df, 'Value')
    analyze_categorical(df, 'Category')
