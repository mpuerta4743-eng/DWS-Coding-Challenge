# Data Platform Engineer - Coding Challenge

## Introduction

You are a Data Platform Engineer tasked with building a pipeline to process end-of-day (EOD) trade data from our Order Management System (OMS).

Every day, you receive two files:
1. `trades.xml`: An XML batch file containing all trades performed during the day.
2. `securities.csv`: A CSV batch file from a security master application containing reference data for the traded securities.

Your goal is to process this data and make it available for downstream consumption by analysts and reporting tools.

## The Challenge

Your task is to build a data pipeline that reads the provided `trades.xml` and `securities.csv` files, processes the data, and stores it in a structured format. You should also provide a design for how you would productionize this pipeline.

### Data Description

- **`trades.xml`**: Contains the details of each trade, including the instrument, quantity, price, side (BUY/SELL), and trade date.
- **`securities.csv`**: Contains reference data for each security, including ISIN, CUSIP, SEDOL, ticker, currency, exchange, and other details.

### Requirements

#### Part 1: Data Engineering

1. **Data Ingestion and Parsing**:
   - Read the `trades.xml` and `securities.csv` files.
2. **Data Transformation and Enrichment**:
   - Join the trade data with the security reference data.
   - Perform data quality checks. At a minimum, ensure that all trades have a corresponding security in the reference data.
   - Enrich the trade data by converting the trade value to a common currency (e.g., USD). You can use a fixed exchange rate for simplicity (e.g., EUR/USD=1.1, GBP/USD=1.25, JPY/USD=0.007, etc.).
3. **Data Storage**:
   - Store the processed and enriched data in a structured format of your choice (e.g., Parquet, SQLite, or any other format you see fit).

#### Part 2: Platform Engineering

1. **Pipeline Design**:
   - Provide a design document (in Markdown) that describes how you would build a production-ready, automated pipeline to run this process daily.
   - Your design should cover the following aspects:
     - **Infrastructure**: What tools, technologies, and cloud services (if any) would you use?
     - **Automation**: How would you schedule the pipeline to run automatically every day?
     - **Error Handling**: How would you handle potential issues like file arrival delays, data quality problems, or processing failures?
     - **Monitoring and Alerting**: How would you monitor the pipeline's health and performance? How would you be alerted if something goes wrong?
     - **Scalability**: How would your design scale if the number of trades increases by 10,000x?

### Deliverables

1. The complete source code for your data processing pipeline.
2. The processed data in the format you have chosen.
3. A `README.md` file with clear instructions on how to set up and run your solution.
4. A `DESIGN.md` file containing your pipeline design.

### Evaluation Criteria

We will evaluate your solution based on the following criteria:
- **Correctness**: Does the pipeline produce the correct output?
- **Code Quality**: Is the code clean, well-structured, and easy to understand?
- **Design**: Is the proposed production pipeline design robust, scalable, and maintainable?
- **Testing**: Have you included unit or integration tests for your code?
- **Documentation**: Is the documentation clear and comprehensive?

### Bonus Points

You can earn bonus points for:
- Containerizing your application (e.g., using Docker).
- Implementing a more sophisticated currency conversion mechanism (e.g., using an external API for exchange rates).
- Adding more advanced data quality checks.
- Providing a dashboard or a way to visualize the processed data.

Good luck!
