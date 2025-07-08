$ email-summarizer --help
Usage: email-summarizer [COMMAND] [ARGS] [OPTIONS]

Commands:
  summarize-file   <path.eml>  
                   Parse and AI-summarize a local .eml file.

  summarize-gmail  <thread_id>  
                   Fetch a Gmail thread by ID and AI-summarize it.

  classify         <snippet>  
                   Classify a short text snippet into one of:
                     Quotation, Order Management, Delivery,
                     Invoice/Tax, Quality Control, Technical Support, Others

  classify-file    <path.eml>  
                   Parse a .eml file and classify its body text.

  classify-gmail   <thread_id>  
                   Fetch a Gmail thread, parse each message, then classify
                   the concatenated thread into one category.

  reply-times-gmail <thread_id> --me <your_email>  
                   Fetch a Gmail thread and compute “how long it took you”
                   to reply to each incoming message.  Requires you to pass
                   your own address via `--me`.

  threads -n/-count N 
                   (Optional) List your most recent N Gmail thread IDs
                   so you can grab the right one to feed into the other
                   commands.  Defaults to the last 10.

Options:
  -h, --help       Show this help message and exit.

Examples:

  # Summarize a saved email:
  email-summarizer summarize-file data/my_convo.eml

  # Summarize a live Gmail thread:
  email-summarizer summarize-gmail 17f3a5b2c4d6e7f8

  # Classify a quick snippet:
  email-summarizer classify "Please send me a quote for 100 items"

  # Classify a whole thread from Gmail:
  email-summarizer classify-gmail 17f3a5b2c4d6e7f8

  # Show reply delays (make sure credentials.json & token.json are in place):
  email-summarizer reply-times-gmail 17f3a5b2c4d6e7f8 --me you@domain.com

  # Get the 10 most recent thread IDs:
  email-summarizer list-threads-gmail --max 10
