read -s -p "DigitalOcean API Access Token:
" TF_VAR_do_token_TEST
export TF_VAR_do_token_TEST

read -s -p "DigitalOcean Spaces access key ID:
" TF_VAR_do_spaces_access_key_id
export TF_VAR_do_spaces_access_key_id

read -s -p "DigitalOcean Spaces secret access key:
" TF_VAR_do_spaces_secret_access_key
export TF_VAR_do_spaces_secret_access_key

echo "
If not deploying new droplets then these can be blank."
read -s -p "DigitalOcean Spaces access key ID for the droplet to use (can be blank):
" TF_VAR_do_app_spaces_access_key_id
export TF_VAR_do_app_spaces_access_key_id

read -s -p "DigitalOcean Spaces secret access key for the droplet to use (can be blank):
" TF_VAR_do_app_spaces_secret_access_key
export TF_VAR_do_app_spaces_secret_access_key
