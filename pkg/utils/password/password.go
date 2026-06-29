package password

import "golang.org/x/crypto/bcrypt"

// bcryptCost 是 bcrypt 的计算成本因子。生产环境推荐 ≥ 12,
// 单次哈希约 250ms,可显著提升抗 GPU 爆破能力。
// 若需更低延迟的测试场景,可调低到 10,但不要低于 bcrypt.MinCost(4)。
const bcryptCost = 12

func HashPassword(password string) (string, error) {
	bytes, err := bcrypt.GenerateFromPassword([]byte(password), bcryptCost)
	if err != nil {
		return "", err
	}
	return string(bytes), nil
}

func CheckPassword(password, hash string) bool {
	err := bcrypt.CompareHashAndPassword([]byte(hash), []byte(password))
	return err == nil
}
