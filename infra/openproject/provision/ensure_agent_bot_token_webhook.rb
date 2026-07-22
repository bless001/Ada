# frozen_string_literal: true

# Idempotent zero-manual OpenProject provisioning.
# Ensures:
# - coding-agent-bot user
# - API token saved to /agent-secrets/openproject_api_token
# - webhook that points to the agent webhook service
# - optional starter project, modules, role binding, and repository binding metadata
# Discovers and reports:
# - work package types, statuses, priorities, and recommended agent custom fields
#
# This uses OpenProject internal Rails models because OpenProject does not expose
# a simple documented REST endpoint for fully provisioning users, tokens, roles,
# project modules, and webhooks from an empty instance.

require "fileutils"
require "json"
require "securerandom"
require "time"

$provisioning_warnings = []


def warn_provisioning(message)
  $provisioning_warnings << message
  puts "WARNING: #{message}"
end


def env_bool(name, default)
  value = ENV.fetch(name, default.to_s).to_s.downcase
  %w[1 true yes y on].include?(value)
end


def env_csv(name, default)
  ENV.fetch(name, default).to_s.split(",").map(&:strip).reject(&:empty?)
end

PROVISIONING_OUTPUT_FILE = ENV.fetch(
  "OP_PROVISIONING_OUTPUT_FILE",
  "/agent-secrets/openproject_provisioning.json"
)
REQUIRED_TYPE_NAMES = env_csv("OP_REQUIRED_WORK_PACKAGE_TYPES", "Epic,Story,Task").freeze
SEMANTIC_STATUS_NAMES = env_csv(
  "OP_SEMANTIC_STATUS_NAMES",
  "Draft,Needs clarification,Awaiting approval,Ready,In progress,Blocked,Ready for verification,Changes required,Verified,Done,Cancelled"
).freeze
REQUIRED_PRIORITY_NAMES = env_csv("OP_REQUIRED_PRIORITIES", "Low,Normal,High,Urgent,Immediate").freeze
REQUIRED_PROJECT_MODULES = env_csv(
  "OP_REQUIRED_PROJECT_MODULES",
  "work_package_tracking,wiki,repository"
).freeze
RECOMMENDED_CUSTOM_FIELDS = [
  { "name" => "Agent Entity ID", "field_format" => "string" },
  { "name" => "Agent Execution Status", "field_format" => "string" },
  { "name" => "Verification Status", "field_format" => "string" },
  { "name" => "Repository Key", "field_format" => "string" },
  { "name" => "Requirement Keys", "field_format" => "string" }
].freeze


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
    true
  elsif record.respond_to?(:has_attribute?) && record.has_attribute?(attr.to_s)
    record[attr.to_s] = value
    true
  else
    false
  end
rescue StandardError => e
  warn_provisioning("Could not set #{record.class.name}.#{attr}: #{e.class}: #{e.message}")
  false
end


def constant_named(name)
  name.to_s.split("::").inject(Object) do |namespace, segment|
    return nil unless namespace.const_defined?(segment)

    namespace.const_get(segment)
  end
end


def safe_public_send(record, method_name)
  return nil unless record.respond_to?(method_name)

  record.public_send(method_name)
rescue StandardError
  nil
end


def record_id(record)
  safe_public_send(record, :id)
end


def record_name(record)
  %i[name login identifier].each do |method_name|
    value = safe_public_send(record, method_name)
    return value.to_s unless value.nil? || value.to_s.empty?
  end

  nil
end


def normalize_name(value)
  value.to_s.downcase.gsub(/[^a-z0-9]+/, " ").strip
end


def resource_summary(record, fallback_name = nil)
  summary = { "available" => !record.nil? }
  summary["id"] = record_id(record) unless record_id(record).nil?
  summary["name"] = record_name(record) || fallback_name unless record_name(record).nil? && fallback_name.nil?
  summary
end


def find_named_record(model, name)
  return nil unless model

  if model.respond_to?(:find_by)
    begin
      exact = model.find_by(name: name)
      return exact unless exact.nil?
    rescue StandardError
      # Fall back to a scan below; some OpenProject models do not expose name.
    end
  end

  if model.respond_to?(:where)
    begin
      exact = model.where(name: name).first
      return exact unless exact.nil?
    rescue StandardError
      # Fall back to a scan below; case-insensitive lookup is enough for reporting.
    end
  end

  if model.respond_to?(:all)
    begin
      target = normalize_name(name)
      return model.all.to_a.find { |record| normalize_name(record_name(record)) == target }
    rescue StandardError
      nil
    end
  end
end


def discover_named_records!(label, model_names, names)
  model = Array(model_names).map { |candidate| constant_named(candidate) }.compact.first

  unless model
    warn_provisioning("Could not discover #{label}; none of these models are available: #{Array(model_names).join(', ')}")
    return names.each_with_object({}) do |name, output|
      output[name] = { "available" => false, "name" => name }
    end
  end

  names.each_with_object({}) do |name, output|
    record = find_named_record(model, name)
    output[name] = resource_summary(record, name).merge("model" => model.name)

    unless record
      warn_provisioning("Required #{label} '#{name}' was not found. Configure it in OpenProject before projecting plans.")
    end
  end
end


def discover_work_package_types!
  discover_named_records!("work package type", ["Type"], REQUIRED_TYPE_NAMES)
end


def discover_statuses!
  discover_named_records!("status", ["Status"], SEMANTIC_STATUS_NAMES)
end


def discover_priorities!
  discover_named_records!("priority", ["IssuePriority", "Priority"], REQUIRED_PRIORITY_NAMES)
end


def custom_field_model
  constant_named("WorkPackageCustomField") || constant_named("CustomField")
end


def ensure_custom_fields!
  model = custom_field_model

  unless model
    warn_provisioning("Could not discover custom fields; no custom field model is available.")
    return RECOMMENDED_CUSTOM_FIELDS.each_with_object({}) do |definition, output|
      output[definition.fetch("name")] = {
        "available" => false,
        "name" => definition.fetch("name"),
        "field_format" => definition.fetch("field_format"),
        "created" => false
      }
    end
  end

  should_create = env_bool("OP_ENSURE_AGENT_CUSTOM_FIELDS", false)

  RECOMMENDED_CUSTOM_FIELDS.each_with_object({}) do |definition, output|
    name = definition.fetch("name")
    record = find_named_record(model, name)
    created = false

    if record.nil? && should_create
      begin
        record = model.new
        set_if_possible(record, :name, name)
        set_if_possible(record, :field_format, definition.fetch("field_format"))
        set_if_possible(record, :is_required, false)
        set_if_possible(record, :required, false)
        set_if_possible(record, :editable, true)
        set_if_possible(record, :searchable, true)
        set_if_possible(record, :visible, true)
        set_if_possible(record, :multi_value, false)
        record.save!
        created = true
      rescue StandardError => e
        warn_provisioning("Could not create custom field '#{name}': #{e.class}: #{e.message}")
        record = find_named_record(model, name)
      end
    elsif record.nil?
      warn_provisioning(
        "Recommended custom field '#{name}' was not found. Set OP_ENSURE_AGENT_CUSTOM_FIELDS=true to let provisioning attempt creation."
      )
    end

    output[name] = resource_summary(record, name).merge(
      "model" => model.name,
      "field_format" => definition.fetch("field_format"),
      "created" => created,
      "ensure_enabled" => should_create
    )
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
  warn_provisioning("Could not force REST API setting: #{e.class}: #{e.message}")
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


def admin_user?(user)
  user.respond_to?(:admin?) && user.admin?
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
  puts "  admin: #{admin_user?(user)}"

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
  webhook_model = constant_named("Webhooks::Webhook")
  raise "Webhooks::Webhook model is not available. Is the webhooks module loaded?" unless webhook_model

  name = ENV.fetch("OP_AGENT_WEBHOOK_NAME", "Coding Agent Webhook")
  url = ENV.fetch("OP_AGENT_WEBHOOK_URL", "http://agent-webhook:8090/webhooks/openproject")
  description = ENV.fetch("OP_AGENT_WEBHOOK_DESCRIPTION", "Coding agent webhook")
  secret = ENV.fetch("OP_AGENT_WEBHOOK_SECRET", "")
  all_projects = env_bool("OP_AGENT_WEBHOOK_ALL_PROJECTS", true)
  events = env_csv(
    "OP_AGENT_WEBHOOK_EVENTS",
    "work_package:created,work_package:updated,work_package_comment:comment"
  )

  webhook = webhook_model.find_or_initialize_by(name: name)
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
      warn_provisioning("Could not find webhook secret attribute. Created webhook without secret.")
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

  webhook
end


def ensure_starter_project!(bot)
  return nil unless env_bool("OP_CREATE_STARTER_PROJECT", false)

  identifier = ENV.fetch("OP_STARTER_PROJECT_IDENTIFIER", "coding-agent-demo")
  name = ENV.fetch("OP_STARTER_PROJECT_NAME", "Coding Agent Demo")

  project = Project.find_or_initialize_by(identifier: identifier)
  project.name = name if project.respond_to?(:name=)

  if project.respond_to?(:description=) && safe_public_send(project, :description).to_s.empty?
    project.description = "Starter project created automatically for coding-agent testing."
  end

  # Required in newer OpenProject versions.
  if project.respond_to?(:workspace_type=)
    project.workspace_type = "project"
  elsif project.respond_to?(:has_attribute?) && project.has_attribute?("workspace_type")
    project["workspace_type"] = "project"
  end

  project.active = true if project.respond_to?(:active=)
  project.public = false if project.respond_to?(:public=)
  project.save!

  puts "Starter project ensured:"
  puts "  identifier: #{project.identifier}"
  puts "  name: #{project.name}"

  project
rescue StandardError => e
  warn_provisioning("Could not create starter project: #{e.class}: #{e.message}")
  nil
end


def ensure_project_modules!(project)
  return {} unless project

  results = {}

  if project.respond_to?(:enabled_module_names) && project.respond_to?(:enabled_module_names=)
    current_modules = Array(project.enabled_module_names).map(&:to_s)
    project.enabled_module_names = (current_modules + REQUIRED_PROJECT_MODULES).uniq
    project.save!
    enabled_modules = Array(project.enabled_module_names).map(&:to_s)

    REQUIRED_PROJECT_MODULES.each do |module_name|
      results[module_name] = { "enabled" => enabled_modules.include?(module_name), "name" => module_name }
    end

    return results
  end

  enabled_module_model = constant_named("EnabledModule")
  unless enabled_module_model
    warn_provisioning("Could not ensure project modules; EnabledModule model is not available.")
    return REQUIRED_PROJECT_MODULES.each_with_object({}) do |module_name, output|
      output[module_name] = { "enabled" => false, "name" => module_name }
    end
  end

  REQUIRED_PROJECT_MODULES.each do |module_name|
    begin
      enabled_module = enabled_module_model.find_or_initialize_by(project_id: project.id, name: module_name)
      enabled_module.save!
      results[module_name] = { "enabled" => true, "id" => record_id(enabled_module), "name" => module_name }
    rescue StandardError => e
      warn_provisioning("Could not enable project module '#{module_name}': #{e.class}: #{e.message}")
      results[module_name] = { "enabled" => false, "name" => module_name }
    end
  end

  results
rescue StandardError => e
  warn_provisioning("Could not ensure project modules: #{e.class}: #{e.message}")
  REQUIRED_PROJECT_MODULES.each_with_object({}) do |module_name, output|
    output[module_name] = { "enabled" => false, "name" => module_name }
  end
end


def ensure_project_role_for_bot!(project, bot)
  return { "assigned" => false, "reason" => "bot_admin" } if admin_user?(bot)

  unless defined?(Role)
    warn_provisioning("Could not ensure bot role; Role model is not available.")
    return { "assigned" => false, "reason" => "role_model_unavailable" }
  end

  role_name = ENV.fetch("OP_AGENT_ROLE_NAME", "Coding Agent")
  requested_permissions = env_csv(
    "OP_AGENT_ROLE_PERMISSIONS",
    "view_work_packages,add_work_packages,edit_work_packages,add_work_package_notes,view_project"
  ).map(&:to_sym)

  role = find_named_record(Role, role_name)
  created = false

  if role.nil?
    role = Role.new
    set_if_possible(role, :name, role_name)
    set_if_possible(role, :builtin, 0)
    created = true
  end

  if role.respond_to?(:permissions=)
    current_permissions = Array(safe_public_send(role, :permissions)).map(&:to_sym)
    role.permissions = (current_permissions + requested_permissions).uniq
  end

  role.save!

  result = resource_summary(role, role_name).merge(
    "created" => created,
    "requested_permissions" => requested_permissions.map(&:to_s),
    "assigned" => false
  )

  if project.nil?
    result["reason"] = "starter_project_disabled"
    return result
  end

  unless defined?(Member)
    warn_provisioning("Could not assign bot to project; Member model is not available.")
    result["reason"] = "member_model_unavailable"
    return result
  end

  member = Member.find_or_initialize_by(project_id: project.id, user_id: bot.id)
  current_roles = member.respond_to?(:roles) ? Array(member.roles) : []
  member.roles = (current_roles + [role]).uniq if member.respond_to?(:roles=)
  member.save!

  result["assigned"] = true
  result["project_identifier"] = safe_public_send(project, :identifier)

  puts "Bot role ensured:"
  puts "  role: #{role.name}"
  puts "  project: #{project.identifier}"
  puts "  permissions: #{requested_permissions.map(&:to_s).join(', ')}"

  result
rescue StandardError => e
  warn_provisioning("Could not ensure bot project role: #{e.class}: #{e.message}")
  { "assigned" => false, "reason" => "error", "error" => "#{e.class}: #{e.message}" }
end


def ensure_sample_project_binding!(project)
  return nil unless project

  repository_key = ENV.fetch("OP_STARTER_REPOSITORY_KEY", "sample-project")
  repository_path = ENV.fetch("OP_STARTER_REPOSITORY_PATH", "/workspace/repositories/sample_project")
  binding_line = "Agent repository binding: #{repository_key} (#{repository_path})"

  if project.respond_to?(:description=)
    description = safe_public_send(project, :description).to_s.strip
    unless description.include?(binding_line)
      project.description = [description, binding_line].reject(&:empty?).join("\n\n")
      project.save!
    end
  end

  {
    "project_id" => record_id(project),
    "project_identifier" => safe_public_send(project, :identifier),
    "repository_key" => repository_key,
    "repository_path" => repository_path
  }
rescue StandardError => e
  warn_provisioning("Could not write starter project repository binding: #{e.class}: #{e.message}")
  nil
end


def webhook_summary(webhook)
  return nil unless webhook

  {
    "id" => record_id(webhook),
    "name" => safe_public_send(webhook, :name),
    "url" => safe_public_send(webhook, :url),
    "enabled" => safe_public_send(webhook, :enabled?),
    "all_projects" => safe_public_send(webhook, :all_projects?),
    "event_names" => Array(safe_public_send(webhook, :event_names)).map(&:to_s)
  }
end


def project_summary(project)
  return nil unless project

  {
    "id" => record_id(project),
    "identifier" => safe_public_send(project, :identifier),
    "name" => safe_public_send(project, :name),
    "active" => safe_public_send(project, :active?),
    "public" => safe_public_send(project, :public?)
  }
end


def write_json_file!(path, payload)
  FileUtils.mkdir_p(File.dirname(path))
  File.write(path, JSON.pretty_generate(payload) + "\n")
  File.chmod(0o600, path)

  puts "Provisioning report written: #{path}"
end


def write_provisioning_report!(bot:, token_file:, webhook:, starter_project:, discoveries:, custom_fields:, project_modules:, project_role:, sample_binding:)
  payload = {
    "generated_at" => Time.now.utc.iso8601,
    "bot_user" => {
      "id" => record_id(bot),
      "login" => safe_public_send(bot, :login),
      "email" => safe_public_send(bot, :mail),
      "admin" => admin_user?(bot)
    },
    "api_token_file" => token_file,
    "work_package_types" => discoveries.fetch("work_package_types"),
    "statuses" => discoveries.fetch("statuses"),
    "priorities" => discoveries.fetch("priorities"),
    "custom_fields" => custom_fields,
    "webhook" => webhook_summary(webhook),
    "starter_project" => project_summary(starter_project),
    "project_modules" => project_modules,
    "project_role" => project_role,
    "sample_binding" => sample_binding,
    "warnings" => $provisioning_warnings.uniq
  }

  write_json_file!(PROVISIONING_OUTPUT_FILE, payload)
  payload
end

ensure_rest_api_enabled!
bot = ensure_bot_user!
token_file = ENV.fetch("OP_AGENT_TOKEN_FILE", "/agent-secrets/openproject_api_token")
create_api_token_for!(bot)

discoveries = {
  "work_package_types" => discover_work_package_types!,
  "statuses" => discover_statuses!,
  "priorities" => discover_priorities!
}
custom_fields = ensure_custom_fields!
webhook = ensure_agent_webhook!
starter_project = ensure_starter_project!(bot)
project_modules = ensure_project_modules!(starter_project)
project_role = ensure_project_role_for_bot!(starter_project, bot)
sample_binding = ensure_sample_project_binding!(starter_project)

write_provisioning_report!(
  bot: bot,
  token_file: token_file,
  webhook: webhook,
  starter_project: starter_project,
  discoveries: discoveries,
  custom_fields: custom_fields,
  project_modules: project_modules,
  project_role: project_role,
  sample_binding: sample_binding
)

puts "OpenProject zero-manual agent provisioning completed."
