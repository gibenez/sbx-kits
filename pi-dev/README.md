# pi-dev
A sanbox development kit based on pi agent, with 
- built-in support for generic llm API (API key only, no OAuth)
- Matt Pocock's skills
- only-cli/oc web-browsing-cli skill
- Playwright cli and its skills

## Run
### Set the llmapi API key
```bash
sbx secret set llmapi
```
### Run sandbox with the pi-dev kit
```bash
sbx run "git+https://github.com/gibenez/sbx-kits.git#dir=pi-dev" --kit-arg llmapi_domain="your.llmapi.domain"
```
### Use it in your ADE or agent orchestrator
```bash
sbx run "git+https://github.com/gibenez/sbx-kits.git#dir=pi-dev" --kit-arg llmapi_domain="your.llmapi.domain" . /var/folders/_j
```
