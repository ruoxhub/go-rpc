package middleware

import (
	"errors"
	"testing"

	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/stretchr/testify/assert"
)

type mockTokenLookup struct {
	user *model.UserInfo
	err  error
}

func (m *mockTokenLookup) FindByToken(token string) (*model.UserInfo, error) {
	return m.user, m.err
}

func setMockTokenRepo(t *testing.T, lookup TokenUserLookup) {
	t.Helper()
	if lookup != nil {
		tokenUserRepoPtr.Store(&lookup)
	} else {
		tokenUserRepoPtr.Store(nil)
	}
}

func TestFindUserByTokenFromDB_Success(t *testing.T) {
	user := &model.UserInfo{ID: 1, UserName: "alice"}
	setMockTokenRepo(t, &mockTokenLookup{user: user})
	defer setMockTokenRepo(t, nil)
	defaultTokenCache.invalidate("good-token")

	got, err := findUserByTokenFromDB("good-token")
	assert.NoError(t, err)
	assert.Equal(t, user, got)
}

func TestFindUserByTokenFromDB_NotFound(t *testing.T) {
	setMockTokenRepo(t, &mockTokenLookup{user: nil, err: nil})
	defer setMockTokenRepo(t, nil)
	defaultTokenCache.invalidate("missing-token")

	got, err := findUserByTokenFromDB("missing-token")
	assert.ErrorIs(t, err, errInvalidToken)
	assert.Nil(t, got)
}

func TestFindUserByTokenFromDB_DBError(t *testing.T) {
	dbErr := errors.New("connection refused")
	setMockTokenRepo(t, &mockTokenLookup{err: dbErr})
	defer setMockTokenRepo(t, nil)

	got, err := findUserByTokenFromDB("any-token")
	assert.ErrorIs(t, err, dbErr)
	assert.Nil(t, got)
}

func TestFindUserByTokenFromDB_RepoNotInitialized(t *testing.T) {
	setMockTokenRepo(t, nil)

	got, err := findUserByTokenFromDB("any-token")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "not initialized")
	assert.Nil(t, got)
}

func TestFindUserByTokenFromDB_EmptyToken(t *testing.T) {
	setMockTokenRepo(t, &mockTokenLookup{user: &model.UserInfo{ID: 1}})
	defer setMockTokenRepo(t, nil)

	got, err := FindUserByToken("")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "empty token")
	assert.Nil(t, got)
}
