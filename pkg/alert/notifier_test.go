package alert

import (
	"net/smtp"
	"testing"
)

func TestSendEmailPlainUsesRecipientAddress(t *testing.T) {
	original := smtpSendMail
	defer func() { smtpSendMail = original }()

	var gotAddr string
	var gotAuth smtp.Auth
	var gotFrom string
	var gotTo []string

	smtpSendMail = func(addr string, auth smtp.Auth, from string, to []string, msg []byte) error {
		gotAddr = addr
		gotAuth = auth
		gotFrom = from
		gotTo = append([]string(nil), to...)
		return nil
	}

	notifier := NewDefaultNotifier()
	notifier.SetSMTPConfig(SMTPConfig{
		Host:   "smtp.example.com",
		Port:   2525,
		From:   "alert@example.com",
		UseTLS: false,
	})

	if err := notifier.SendEmail("ops@example.com", "subject", "body"); err != nil {
		t.Fatalf("SendEmail() error = %v", err)
	}

	if gotAddr != "smtp.example.com:2525" {
		t.Fatalf("addr = %s, want %s", gotAddr, "smtp.example.com:2525")
	}
	if gotAuth != nil {
		t.Fatalf("expected nil auth for plain SMTP")
	}
	if gotFrom != "alert@example.com" {
		t.Fatalf("from = %s, want %s", gotFrom, "alert@example.com")
	}
	if len(gotTo) != 1 || gotTo[0] != "ops@example.com" {
		t.Fatalf("to = %v, want [ops@example.com]", gotTo)
	}
}

func TestSendEmailTLSUsesConfiguredAddressAndRecipient(t *testing.T) {
	original := smtpSendMail
	defer func() { smtpSendMail = original }()

	var gotAddr string
	var gotTo []string

	smtpSendMail = func(addr string, auth smtp.Auth, from string, to []string, msg []byte) error {
		gotAddr = addr
		gotTo = append([]string(nil), to...)
		return nil
	}

	notifier := NewDefaultNotifier()
	notifier.SetSMTPConfig(SMTPConfig{
		Host:     "smtp.example.com",
		Port:     587,
		Username: "user",
		Password: "pass",
		From:     "alert@example.com",
		UseTLS:   true,
	})

	if err := notifier.SendEmail("ops@example.com", "subject", "body"); err != nil {
		t.Fatalf("SendEmail() error = %v", err)
	}

	if gotAddr != "smtp.example.com:587" {
		t.Fatalf("addr = %s, want %s", gotAddr, "smtp.example.com:587")
	}
	if len(gotTo) != 1 || gotTo[0] != "ops@example.com" {
		t.Fatalf("to = %v, want [ops@example.com]", gotTo)
	}
}
