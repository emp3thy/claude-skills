package com.acme.shipments;

import jakarta.jms.ConnectionFactory;
import org.apache.qpid.jms.JmsConnectionFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

/** AMQP 1.0 over Qpid JMS, the protocol the real services speak (design spec 11). */
@Configuration
public class JmsConfig {
    @Bean
    ConnectionFactory connectionFactory(@Value("${amq.url}") String url,
                                        @Value("${amq.user}") String user,
                                        @Value("${amq.password}") String password) {
        JmsConnectionFactory factory = new JmsConnectionFactory(url);
        factory.setUsername(user);
        factory.setPassword(password);
        return factory;
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }
}
