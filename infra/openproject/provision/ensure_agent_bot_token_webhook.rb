# frozen_string_literal: true

# Idempotent zero-manual OpenProject provisioning.
# Creates:
# - coding-agent-bot user
# - admin permission for MVP
# - API token saved to /agent-secrets/openproject_api_token
# - webhook that points to the agent webhook service
# - optional starter project
#
# This uses OpenProject internal Rails models because OpenProject does not expose
# a simple documented REST endpoint for fully provisioning users, tokens, and
# webhooks from an empty instance.

require "securerandom"
require "fileutils"


def env_bool(name, default)
  value = ENV.fetch(name, default.to_s).to_s.downcase
  %w[1 true yes y].include?(value)
end



def generate_policy_compliant_password(length = 48)
  lowercase = ("a".."z").to_a
  uppercase = ("A".."Z").to_a
  numbers = ("0".."9").to_a
  special = %w[! @ # $ % ^ & * - _ + = ?]
  all = lowercase + uppercase + numbers + special

  password_chars = [
    lowercase.sample,
    uppercase.sample,
    numbers.sample,
    special.sample
  ]

  (length - password_chars.length).times do
    password_chars << all.sample
  end

  password_chars.shuffle.join
end

def set_if_possible(record, attr, value)
  setter = "#{attr}="
  if record.respond_to?(setter)
    record.public_send(setter, value)
  elsif record.respond_to?(:has_attribute?) && record.has_attribute?(attr.to_s)
    record[attr.to_s] = value
  end
end


def ensure_rest_api_enabled!
  return unless defined?(Setting)

  if Setting.respond_to?(:rest_api_enabled=)
    Setting.rest_api_enabled = true
  else
    begin
      Setting["rest_api_enabled"] = true if Setting.respond_to?(:[]=)
    rescue StandardError
      # Ignore if this setting is not writable in this version.
    end
  end
rescue StandardError => e
  puts "WARNING: Could not force REST API setting: #{e.class}: #{e.message}"
end


def ensure_active!(user)
  if user.respond_to?(:activate!)
    user.activate!
  elsif defined?(Principal) && Principal.const_defined?(:STATUSES) && user.respond_to?(:status=)
    user.status = Principal::STATUSES[:active]
    user.save!
  elsif user.respond_to?(:status=)
    user.status = 1
    user.save!
  end
end


def ensure_bot_user!
  login = ENV.fetch("OP_AGENT_LOGIN", "coding-agent-bot")
  email = ENV.fetch("OP_AGENT_EMAIL", "coding-agent-bot@example.local")
  firstname = ENV.fetch("OP_AGENT_FIRSTNAME", "Coding")
  lastname = ENV.fetch("OP_AGENT_LASTNAME", "Agent")
  admin = env_bool("OP_AGENT_ADMIN", true)

  user = User.find_or_initialize_by(login: login)
  user.firstname = firstname
  user.lastname = lastname
  user.mail = email
  set_if_possible(user, :language, "en")
  set_if_possible(user, :admin, admin)

  if user.new_record?
    password = generate_policy_compliant_password(64)
    user.password = password if user.respond_to?(:password=)
    user.password_confirmation = password if user.respond_to?(:password_confirmation=)
  end

  user.save!
  ensure_active!(user)

  puts "Bot user ensured:"
  puts "  login: #{user.login}"
  puts "  id: #{user.id}"
  puts "  admin: #{user.admin? if user.respond_to?(:admin?)}"

  user
end


def token_file_has_value?(path)
  File.exist?(path) && !File.read(path).strip.empty?
end


def create_api_token_for!(user)
  token_file = ENV.fetch("OP_AGENT_TOKEN_FILE", "/agent-secrets/openproject_api_token")
  FileUtils.mkdir_p(File.dirname(token_file))

  if token_file_has_value?(token_file)
    puts "API token file already exists. Keeping existing token: #{token_file}"
    return File.read(token_file).strip
  end

  token_value = nil

  if defined?(Token::API) && Token::API.respond_to?(:create_and_return_value)
    begin
      token_value = Token::API.create_and_return_value(user)
    rescue ArgumentError
      begin
        token_value = Token::API.create_and_return_value(user: user)
      rescue StandardError
        token_value = nil
      end
    end
  end

  if token_value.nil? && defined?(Token::API)
    token = Token::API.new
    set_if_possible(token, :user, user)
    set_if_possible(token, :name, "coding-agent")
    set_if_possible(token, :value, SecureRandom.hex(32))
    token.save!
    token_value = token.respond_to?(:plain_value) ? token.plain_value : token.value
  end

  raise "Could not create OpenProject API token" if token_value.nil? || token_value.empty?

  File.write(token_file, token_value)
  File.chmod(0o600, token_file)

  puts "API token created for bot user."
  puts "  token file: #{token_file}"
  token_value
end


def ensure_agent_webhook!
  unless defined?(Webhooks::Webhook)
    raise "Webhooks::Webhook model is not available. Is the webhooks module loaded?"
  end

  name = ENV.fetch("OP_AGENT_WEBHOOK_NAME", "Coding Agent Webhook")
  url = ENV.fetch("OP_AGENT_WEBHOOK_URL", "http://agent-webhook:8090/webhooks/openproject")
  description = ENV.fetch("OP_AGENT_WEBHOOK_DESCRIPTION", "Coding agent webhook")
  secret = ENV.fetch("OP_AGENT_WEBHOOK_SECRET", "")
  all_projects = env_bool("OP_AGENT_WEBHOOK_ALL_PROJECTS", true)

  events = ENV.fetch(
    "OP_AGENT_WEBHOOK_EVENTS",
    "work_package:created,work_package:updated,work_package_comment:comment"
  ).split(",").map(&:strip).reject(&:empty?)

  webhook = Webhooks::Webhook.find_or_initialize_by(name: name)
  webhook.url = url
  webhook.enabled = true
  webhook.all_projects = all_projects
  set_if_possible(webhook, :description, description)

  unless secret.empty?
    if webhook.respond_to?(:secret=)
      webhook.secret = secret
    elsif webhook.respond_to?(:has_attribute?) && webhook.has_attribute?("secret")
      webhook["secret"] = secret
    elsif webhook.respond_to?(:has_attribute?) && webhook.has_attribute?("signature_secret")
      webhook["signature_secret"] = secret
    else
      puts "WARNING: Could not find webhook secret attribute. Created webhook without secret."
    end
  end

  webhook.event_names = events
  webhook.save!

  puts "Webhook ensured:"
  puts "  name: #{webhook.name}"
  puts "  url: #{webhook.url}"
  puts "  enabled: #{webhook.enabled?}"
  puts "  all_projects: #{webhook.all_projects?}"
  puts "  events: #{webhook.event_names.join(', ')}"
end

def ensure_starter_project!(bot)
  return unless env_bool("OP_CREATE_STARTER_PROJECT", false)

  identifier = ENV.fetch("OP_STARTER_PROJECT_IDENTIFIER", "coding-agent-demo")
  name = ENV.fetch("OP_STARTER_PROJECT_NAME", "Coding Agent Demo")

  project = Project.find_or_initialize_by(identifier: identifier)

  project.name = name if project.respond_to?(:name=)

  if project.respond_to?(:description=)
    project.description = "Starter project created automatically for coding-agent testing."
  end

  # Required in newer OpenProject versions.
  if project.respond_to?(:workspace_type=)
    project.workspace_type = "project"
  elsif project.respond_to?(:has_attribute?) && project.has_attribute?("workspace_type")
    project["workspace_type"] = "project"
  end

  project.active = true if project.respond_to?(:active=)

  # Optional: keep the starter project private.
  project.public = false if project.respond_to?(:public=)

  project.save!

  puts "Starter project ensured:"
  puts "  identifier: #{project.identifier}"
  puts "  name: #{project.name}"

  # If bot is admin this is not strictly needed, but it keeps the relationship clear.
  if defined?(Member) && defined?(Role) && !bot.admin?
    role = Role.where(builtin: 0).first || Role.first

    if role
      member = Member.find_or_initialize_by(project_id: project.id, user_id: bot.id)
      member.roles = [role]
      member.save!

      puts "Bot added as project member with role: #{role.name}"
    end
  end
rescue StandardError => e
  puts "WARNING: Could not create starter project: #{e.class}: #{e.message}"
end

# def ensure_starter_project!(bot)
#   return unless env_bool("OP_CREATE_STARTER_PROJECT", false)

#   identifier = ENV.fetch("OP_STARTER_PROJECT_IDENTIFIER", "coding-agent-demo")
#   name = ENV.fetch("OP_STARTER_PROJECT_NAME", "Coding Agent Demo")

#   project = Project.find_or_initialize_by(identifier: identifier)
#   project.name = name if project.respond_to?(:name=)
#   project.description = "Starter project created automatically for coding-agent testing." if project.respond_to?(:description=)
#   project.active = true if project.respond_to?(:active=)
#   project.save!

#   puts "Starter project ensured:"
#   puts "  identifier: #{project.identifier}"
#   puts "  name: #{project.name}"

#   # If bot is admin this is not strictly needed, but it keeps the relationship clear.
#   if defined?(Member) && defined?(Role) && !bot.admin?
#     role = Role.where(builtin: 0).first || Role.first
#     if role
#       member = Member.find_or_initialize_by(project_id: project.id, user_id: bot.id)
#       member.roles = [role]
#       member.save!
#       puts "Bot added as project member with role: #{role.name}"
#     end
#   end
# rescue StandardError => e
#   puts "WARNING: Could not create starter project: #{e.class}: #{e.message}"
# end

ensure_rest_api_enabled!
bot = ensure_bot_user!
create_api_token_for!(bot)
ensure_agent_webhook!
ensure_starter_project!(bot)

puts "OpenProject zero-manual agent provisioning completed."
