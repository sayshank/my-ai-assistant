# Email Analytics Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    DATA INGESTION                                        │
└─────────────────────────────────────────────────────────────────────────────────────────┘

    ┌─────────┐         ┌──────────────────┐         ┌─────────────────┐
    │  Gmail  │────────▶│  Durable Lambda  │────────▶│   S3 (gmail-s3) │
    │   API   │         │ gmail-to-s3-     │         │   /raw/*.json   │
    └─────────┘         │ durable          │         └────────┬────────┘
                        └──────────────────┘                  │
                         • OAuth2 auth                        │
                         • Checkpointed                       │
                         • 67K+ emails                        │
                                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                  DATA TRANSFORMATION                                     │
└─────────────────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────┐         ┌──────────────────┐         ┌─────────────────────────┐
    │   S3 (gmail-s3) │────────▶│   Glue PySpark   │────────▶│      S3 Tables          │
    │   /raw/*.json   │         │   Job            │         │  (Iceberg Format)       │
    └─────────────────┘         └──────────────────┘         │                         │
                                 • Glue 5.0                   │  communications-table-  │
                                 • Parse JSON                 │  bucket                 │
                                 • Extract fields             │  .my_communications     │
                                                              │  .messages              │
                                                              └───────────┬─────────────┘
                                                                          │
                                                                          │
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   QUERY INTERFACES                                       │
└─────────────────────────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────────────┐
                    │                                         │
          ┌─────────┴─────────┐                   ┌───────────┴───────────┐
          ▼                   ▼                   ▼                       ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│    Redshift      │  │   Bedrock KB     │  │  Glue PySpark    │  │   OpenSearch     │
│   Serverless     │  │   (SQL Type)     │  │  Embed Job       │  │   Serverless     │
│                  │  │                  │  │                  │  │                  │
│ email-analytics  │  │  KB: FRE4X7GTZR  │  │ embed-emails-to- │  │  email-vectors   │
│ -wg              │  │                  │  │ opensearch       │  │  collection      │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                     │                     │                     │
         │                     │                     │                     │
         ▼                     ▼                     ▼                     ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   SQL Queries    │  │  Natural Lang    │  │  Bedrock Titan   │  │  Vector Search   │
│                  │  │  Questions       │  │  Embeddings      │  │  (Semantic)      │
│ • Ad-hoc SQL     │  │                  │  │                  │  │                  │
│ • Analytics      │  │ "How many emails │  │ • Subject line   │  │ "Find emails     │
│ • Joins          │  │  from John?"     │  │   embeddings     │  │  about project   │
│                  │  │                  │  │ • 1024 dims      │  │  deadlines"      │
└──────────────────┘  └──────────────────┘  └──────────────────┘  └──────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   DATA FLOW SUMMARY                                      │
└─────────────────────────────────────────────────────────────────────────────────────────┘

  Gmail API ──▶ S3 Raw JSON ──▶ S3 Tables (Iceberg) ──┬──▶ Redshift (SQL)
                                                      │
                                                      ├──▶ Bedrock KB (NL queries)
                                                      │
                                                      └──▶ OpenSearch (Vector search)


┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   KEY RESOURCES                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘

  S3 Bucket:           gmail-s3
  S3 Tables Bucket:    communications-table-bucket
  S3 Tables Namespace: my_communications
  S3 Tables Table:     messages
  
  Redshift Workgroup:  email-analytics-wg
  Redshift Database:   emaildb
  Redshift Table:      public.email_messages
  
  Bedrock KB ID:       FRE4X7GTZR
  
  OpenSearch Collection: email-vectors
  OpenSearch Endpoint:   rk83x6g2j4ng2xm29ip5.eu-central-1.aoss.amazonaws.com
  OpenSearch Index:      email-embeddings
  
  Region:              eu-central-1
  Account:             449613704053
```
