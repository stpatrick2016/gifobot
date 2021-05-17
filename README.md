# GIF-O-Bot
Telegram Bot that searches for GIF files

### Configuration:
The following environment variables are required for running the bot:

|Variable|Description|
|--------|-----------|
|GOOGLE_API_TOKEN|Custom search API token. Get one [here](https://developers.google.com/custom-search/v1/overview).|
|GOOGLE_SEARCH_CONTEXT|Search context ID. More details [here](https://developers.google.com/custom-search/v1/using_rest).|
|GOOGLE_PROJECT_ID|Google cloud project ID or number, used by translation. See [here](https://cloud.google.com/translate/docs/setup) how to configure|
|SEARCH_CATEGORY|*Optional*. A keyword to add to every search. In case you want to stick to specific context.|
|TELEGRAM_API_TOKEN|Telegram Bot API token. Guide can be found [here](https://core.telegram.org/bots).|
|GOOGLE_CREDENTIALS_SECRET_NAME|*Optional*. AWS SecretsManager secret name to lookup for Google Service Account credentials for translations. Look [here](https://cloud.google.com/docs/authentication/production#create_service_account) on how to create such account. Make sure to grant Cloud Translation API User role to the account. <br/>If not specified, automatic translation to English will not be performed.|

