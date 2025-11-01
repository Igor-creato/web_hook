API Documentation
Endpoints
Health Check
text
GET /health
Returns service health status and configuration info.

Response:

json
{
"status": "healthy",
"service": "epn-bz-webhook-receiver-with-errors",
"version": "4.0.0",
"secret_configured": true,
"email_configured": true
}
Root Information
text
GET /
Returns service information and configuration details.

Webhook Endpoint
text
POST /webhook/{secret_token}
GET /webhook/{secret_token}
Parameters:

secret_token: Secret authentication token in URL path

Headers:

Content-Type: application/json (for POST)

User-Agent: Client user agent

Query Parameters (EPN.bz):

click_id (required): User ID from your system

order_number (required): Order number

uniq_id: Unique order ID in EPN.bz

order_status: Order status (waiting/pending/completed/rejected)

revenue: Order amount

commission_fee: Commission amount

currency: Currency code (RUB, USD, EUR, GBP, TON)

offer_name: Offer name

sub, sub2, sub3, sub4, sub5: Custom parameters

Success Response (200):

json
{
"status": "success",
"partner": "epn_bz",
"click_id": "123",
"uniq_id": "EPN-12345",
"order_status": "completed",
"revenue": 1500.0,
"commission_fee": 100.0,
"processing_time": "0.045s",
"message": "EPN.bz webhook processed and saved successfully",
"database_status": "healthy"
}
Database Error Response (503):

json
{
"detail": "Database temporarily unavailable, please retry later"
}
Invalid Token Response (401):

json
{
"detail": "Invalid secret token"
}
Error Codes
Code Description Action
200 Success Continue
401 Invalid secret token Check token
400 Invalid request data Fix request format
503 Database unavailable Retry (automatic via Svix)
500 Internal server error Contact support
Rate Limiting
No explicit rate limiting implemented. Svix handles retry logic automatically.

Authentication
Authentication is performed via secret token in URL path:

text
/webhook/your_secret_token_here
The token is a 64-character hexadecimal string generated during installation.
